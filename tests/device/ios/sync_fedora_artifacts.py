#!/usr/bin/env python3
"""Dispatch, download, verify, and activate the signed iOS Fedora handoff."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile


DEVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = DEVICE_ROOT.parents[1]
VERIFIER = Path(__file__).with_name("verify_fedora_artifacts.py")
PERSONAL_TEAM_VERIFIER = Path(__file__).with_name("verify_personal_team_artifacts.py")
IOS_ROOT = Path(__file__).resolve().parent
if str(IOS_ROOT) not in sys.path:
    sys.path.insert(0, str(IOS_ROOT))
from security_tools import install as install_security_tools  # noqa: E402
API_VERSION = "2026-03-10"
DEFAULT_REPOSITORY = "noah-be/overte"
WORKFLOW = "ios-bootstrap.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW}"
PROTECTED_REF = "apple-ios"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OVERTE_IPA_RE = re.compile(r"^[0-9]{4,}-OverteIOSClient-Release-device-signed[.]ipa$")
WDA_IPA = "WebDriverAgentRunner-Runner-16.8.0-signed.ipa"
PERSONAL_OVERTE_IPA = "Overte-PersonalTeam-E2E-signed.ipa"
PERSONAL_WDA_IPA = "WebDriverAgentRunner-16.8.0-PersonalTeam-signed.ipa"
PROTECTED_RECEIPT = "overte-ios-fedora-e2e-receipt-v1"
PERSONAL_RECEIPT = "overte-ios-personal-team-artifact-receipt-v1"
PREINSTALLED_RECEIPT = "overte-ios-personal-team-preinstalled-receipt-v1"
PINNED_SERVICE_RUNTIME = Path("/usr/local/lib/overte-ios-remotexpc/5.15.3-r3")
MAX_ACTIONS_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
MAX_ENCRYPTED_BYTES = 4 * 1024 * 1024 * 1024
MAX_INNER_ZIP_BYTES = 4 * 1024 * 1024 * 1024
MAX_IPA_BYTES = 4 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARCHIVE_ENTRIES = 8
SCENE_PATH = "/scene.json?location=%2F0%2C2%2C4%2F0%2C0%2C0%2C1"


class HandoffError(ValueError):
    """The authenticated Actions handoff failed closed."""


def fail(message: str) -> "NoReturn":
    raise HandoffError(message)


def private_directory(path: Path) -> Path:
    if has_symlink_component(path) or (path.exists() and not path.is_dir()):
        fail("private handoff path must be a real directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(stat.S_IRWXU)
    return path


def secure_json(path: Path, value: dict) -> None:
    if not path.is_absolute() or has_symlink_component(path):
        fail("private JSON path must be absolute and non-symlinked")
    private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.close(descriptor)
        descriptor = -1
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def has_symlink_component(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
        if not current.exists():
            break
    return False


def inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPOSITORY_ROOT.resolve())
        return True
    except ValueError:
        return False


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow only GitHub's HTTPS artifact redirects without forwarding auth."""

    @staticmethod
    def allowed(host: str) -> bool:
        host = host.lower().rstrip(".")
        return (
            host == "api.github.com"
            or host.endswith(".blob.core.windows.net")
            or host.endswith(".actions.githubusercontent.com")
            or host.endswith(".githubusercontent.com")
        )

    def redirect_request(self, request, fp, code, msg, headers, new_url):
        parsed = urllib.parse.urlparse(new_url)
        if parsed.scheme != "https" or not parsed.hostname or not self.allowed(parsed.hostname):
            fail("GitHub returned an unsafe artifact redirect")
        redirected = super().redirect_request(request, fp, code, msg, headers, new_url)
        if redirected is not None and parsed.hostname.lower() != "api.github.com":
            redirected.remove_header("Authorization")
        return redirected


class GitHubApi:
    def __init__(self, repository: str, token: str, *, opener=None):
        if not REPOSITORY_RE.fullmatch(repository):
            fail("repository must have the form owner/name")
        if not token or "\n" in token or "\r" in token:
            fail("OVERTE_GITHUB_TOKEN is required and must be a single line")
        self.repository = repository
        self.token = token
        self.opener = opener or urllib.request.build_opener(SafeRedirectHandler())
        self.base = f"https://api.github.com/repos/{repository}"

    def request(self, method: str, url: str, payload: dict | None = None):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.github.com":
            fail("refusing a non-GitHub API request")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, method=method, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "overte-fedora-ios-device-lab/1",
        })
        try:
            with self.opener.open(request, timeout=60) as response:
                data = response.read(4 * 1024 * 1024 + 1)
                if len(data) > 4 * 1024 * 1024:
                    fail("GitHub API response exceeded the safety limit")
                if not data:
                    return {}
                value = json.loads(data)
                if not isinstance(value, dict):
                    fail("GitHub API returned an unexpected response")
                return value
        except urllib.error.HTTPError as error:
            fail(f"GitHub API request failed with HTTP {error.code}")
        except urllib.error.URLError as error:
            fail(f"GitHub API request failed: {type(error.reason).__name__}")

    def dispatch(self, inputs: dict[str, str]) -> int:
        workflow = urllib.parse.quote(WORKFLOW, safe="")
        response = self.request(
            "POST", f"{self.base}/actions/workflows/{workflow}/dispatches",
            {"ref": PROTECTED_REF, "inputs": inputs, "return_run_details": True},
        )
        run_id = response.get("workflow_run_id")
        if not isinstance(run_id, int) or run_id <= 0:
            fail("GitHub dispatch did not return the workflow run ID")
        return run_id

    def run(self, run_id: int) -> dict:
        return self.request("GET", f"{self.base}/actions/runs/{run_id}")

    def artifacts(self, run_id: int) -> list[dict]:
        payload = self.request("GET", f"{self.base}/actions/runs/{run_id}/artifacts?per_page=100")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list) or payload.get("total_count") != len(artifacts):
            fail("GitHub returned an incomplete artifact list")
        if not all(isinstance(item, dict) for item in artifacts):
            fail("GitHub returned invalid artifact metadata")
        return artifacts

    def download(self, url: str, destination: Path) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "api.github.com":
            fail("artifact download URL is outside the GitHub API")
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "overte-fedora-ios-device-lab/1",
        })
        try:
            with self.opener.open(request, timeout=120) as response, destination.open("xb") as output:
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > MAX_ACTIONS_ARCHIVE_BYTES:
                        fail("GitHub artifact exceeded the download safety limit")
                    output.write(block)
        except urllib.error.HTTPError as error:
            fail(f"GitHub artifact download failed with HTTP {error.code}")
        except urllib.error.URLError as error:
            fail(f"GitHub artifact download failed: {type(error.reason).__name__}")


def verify_run(run: dict, run_id: int, *, expected_attempt: int,
               require_complete: bool) -> dict:
    path = run.get("path")
    repository = run.get("repository")
    head_repository = run.get("head_repository")
    if (
        run.get("id") != run_id
        or run.get("event") != "workflow_dispatch"
        or path not in {
            WORKFLOW_PATH,
            f"{WORKFLOW_PATH}@{PROTECTED_REF}",
            f"{WORKFLOW_PATH}@refs/heads/{PROTECTED_REF}",
        }
        or run.get("head_branch") != PROTECTED_REF
        or not isinstance(run.get("head_sha"), str)
        or not REVISION_RE.fullmatch(run["head_sha"])
        or not isinstance(repository, dict)
        or repository.get("full_name") != DEFAULT_REPOSITORY
        or not isinstance(repository.get("id"), int)
        or repository["id"] <= 0
        or not isinstance(head_repository, dict)
        or head_repository.get("full_name") != DEFAULT_REPOSITORY
        or head_repository.get("id") != repository["id"]
        or run.get("run_attempt") != expected_attempt
    ):
        fail("workflow run is outside the protected iOS producer boundary")
    if require_complete and (run.get("status") != "completed" or run.get("conclusion") != "success"):
        fail("protected iOS producer did not complete successfully")
    return run


def wait_for_run(api: GitHubApi, run_id: int, expected_attempt: int,
                 timeout_seconds: int, poll_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        run = verify_run(
            api.run(run_id), run_id, expected_attempt=expected_attempt, require_complete=False
        )
        if run.get("status") == "completed":
            return verify_run(
                run, run_id, expected_attempt=expected_attempt, require_complete=True
            )
        if time.monotonic() >= deadline:
            fail("timed out waiting for the protected iOS producer")
        time.sleep(poll_seconds)


def select_artifacts(items: list[dict], run: dict) -> dict[str, dict]:
    expected = {
        "overte": f"ios-fedora-e2e-overte-{run['id']}-{run['run_attempt']}",
        "wda": f"ios-fedora-e2e-wda-{run['id']}-{run['run_attempt']}",
    }
    selected: dict[str, dict] = {}
    for role, name in expected.items():
        matches = [item for item in items if item.get("name") == name]
        if len(matches) != 1:
            fail(f"protected producer must expose exactly one {role} artifact")
        item = matches[0]
        workflow_run = item.get("workflow_run")
        digest = item.get("digest")
        if (
            item.get("expired") is not False
            or not isinstance(item.get("id"), int)
            or not isinstance(item.get("archive_download_url"), str)
            or not isinstance(digest, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or not isinstance(workflow_run, dict)
            or workflow_run.get("id") != run["id"]
            or workflow_run.get("repository_id") != run["repository"]["id"]
            or workflow_run.get("head_repository_id") != run["repository"]["id"]
            or workflow_run.get("head_branch") != PROTECTED_REF
            or workflow_run.get("head_sha") != run["head_sha"]
            or item["archive_download_url"]
            != f"https://api.github.com/repos/{DEFAULT_REPOSITORY}/actions/artifacts/{item['id']}/zip"
        ):
            fail(f"{role} artifact provenance is invalid")
        selected[role] = item
    return selected


def copy_zip_member(archive: zipfile.ZipFile, entry: zipfile.ZipInfo,
                    target: Path, limit: int, label: str) -> None:
    if entry.file_size <= 0 or entry.file_size > limit:
        fail(f"{label} declared size is invalid")
    if entry.compress_type != zipfile.ZIP_STORED or entry.compress_size != entry.file_size:
        fail(f"{label} must use the producer's non-compressing ZIP contract")
    total = 0
    try:
        with archive.open(entry) as source, target.open("xb") as output:
            while block := source.read(min(1024 * 1024, limit - total + 1)):
                total += len(block)
                if total > limit:
                    fail(f"{label} exceeded its extraction limit")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if total != entry.file_size:
            fail(f"{label} extracted size differs from ZIP metadata")
        target.chmod(0o600)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def safe_extract(archive_path: Path, destination: Path, role: str) -> tuple[Path, Path]:
    if (archive_path.is_symlink() or not archive_path.is_file()
            or archive_path.stat().st_size > MAX_INNER_ZIP_BYTES):
        fail(f"{role} decrypted inner ZIP size is invalid")
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile):
        fail(f"{role} workflow artifact is not a valid ZIP")
    with archive:
        entries = archive.infolist()
        if len(entries) != 2 or len(entries) > MAX_ARCHIVE_ENTRIES:
            fail(f"{role} workflow artifact must contain exactly two files")
        names: set[str] = set()
        total = 0
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            mode = (entry.external_attr >> 16) & 0o170000
            if (
                path.is_absolute()
                or len(path.parts) != 1
                or any(part in {"", ".", ".."} for part in path.parts)
                or "\\" in name
                or name in names
                or entry.is_dir()
                or entry.flag_bits & 0x1
                or mode not in {0, stat.S_IFREG}
            ):
                fail(f"{role} workflow artifact contains an unsafe entry")
            limit = MAX_IPA_BYTES if name.endswith(".ipa") else MAX_MANIFEST_BYTES
            if entry.file_size <= 0 or entry.file_size > limit:
                fail(f"{role} workflow artifact entry size is invalid")
            if entry.compress_type != zipfile.ZIP_STORED or entry.compress_size != entry.file_size:
                fail(f"{role} workflow artifact violates the stored inner-ZIP contract")
            total += entry.file_size
            names.add(name)
        if total > MAX_IPA_BYTES + MAX_MANIFEST_BYTES:
            fail(f"{role} workflow artifact expands beyond the cumulative limit")
        ipa_names = [name for name in names if name.endswith(".ipa")]
        manifest_names = [name for name in names if name.endswith(".manifest.json")]
        if len(ipa_names) != 1 or len(manifest_names) != 1:
            fail(f"{role} workflow artifact does not contain an IPA/manifest pair")
        ipa_name = ipa_names[0]
        if role == "overte" and not OVERTE_IPA_RE.fullmatch(ipa_name):
            fail("Overte workflow artifact IPA name is invalid")
        if role == "wda" and ipa_name != WDA_IPA:
            fail("WDA workflow artifact IPA name is invalid")
        if manifest_names[0] != ipa_name.removesuffix(".ipa") + ".manifest.json":
            fail(f"{role} workflow manifest name does not match its IPA")
        private_directory(destination)
        for entry in entries:
            target = destination / entry.filename
            limit = MAX_IPA_BYTES if entry.filename.endswith(".ipa") else MAX_MANIFEST_BYTES
            copy_zip_member(
                archive, entry, target, limit, f"{role} inner {entry.filename}"
            )
        return destination / ipa_name, destination / manifest_names[0]


def extract_encrypted_payload(archive_path: Path, destination: Path,
                              expected_name: str, role: str) -> Path:
    if (archive_path.is_symlink() or not archive_path.is_file()
            or archive_path.stat().st_size > MAX_ACTIONS_ARCHIVE_BYTES):
        fail(f"{role} Actions archive size is invalid")
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile):
        fail(f"{role} workflow artifact is not a valid ZIP")
    with archive:
        entries = archive.infolist()
        if len(entries) != 1 or entries[0].filename != expected_name:
            fail(f"{role} workflow artifact must contain its one encrypted payload")
        entry = entries[0]
        mode = (entry.external_attr >> 16) & 0o170000
        if (
            entry.is_dir() or entry.flag_bits & 0x1 or mode not in {0, stat.S_IFREG}
            or not 0 < entry.file_size <= MAX_ENCRYPTED_BYTES
            or entry.compress_type != zipfile.ZIP_STORED
            or entry.compress_size != entry.file_size
        ):
            fail(f"{role} encrypted workflow payload is unsafe")
        target = destination / expected_name
        copy_zip_member(
            archive, entry, target, MAX_ENCRYPTED_BYTES, f"{role} encrypted payload"
        )
        return target


def private_age_identity() -> Path:
    value = os.environ.get("OVERTE_IOS_AGE_IDENTITY_FILE", "")
    path = Path(value).expanduser()
    if (not value or has_symlink_component(path) or not path.is_absolute()
            or not path.is_file()):
        fail("OVERTE_IOS_AGE_IDENTITY_FILE must name an absolute private age identity file")
    metadata = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1):
        fail("age identity file must be an owned, unlinked regular file")
    if os.name != "nt" and metadata.st_mode & 0o077:
        fail("age identity file must not be accessible to group or other users")
    return path


def decrypt_payload(age: Path, identity: Path, encrypted: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        fail("age output must be a new private file")
    try:
        result = subprocess.run(
            [str(age), "--decrypt", "--identity", str(identity),
             "--output", str(destination), str(encrypted)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15 * 60, check=False,
        )
        if (result.returncode or destination.is_symlink() or not destination.is_file()
                or not 0 < destination.stat().st_size <= MAX_INNER_ZIP_BYTES):
            fail("signed iOS workflow payload failed bounded authenticated age decryption")
        destination.chmod(0o600)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def activate_target(config_path: Path, selector: str, receipt_path: Path) -> None:
    if (has_symlink_component(config_path) or not config_path.is_absolute()
            or not config_path.is_file() or inside_repository(config_path)
            or inside_repository(receipt_path)):
        fail("iOS target configuration must be an existing absolute private file")
    metadata = config_path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1 or metadata.st_mode & 0o077):
        fail("iOS target configuration must be an owned mode-0600 private file")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("iOS target configuration or artifact receipt is unreadable")
    targets = config.get("targets") if isinstance(config, dict) else None
    if not isinstance(targets, list):
        fail("iOS target configuration has an invalid shape")
    matches = [item for item in targets if isinstance(item, dict) and item.get("selector") == selector]
    if len(matches) != 1 or matches[0].get("platform") != "ios":
        fail("private selector does not identify exactly one iOS target")
    target = matches[0]
    capabilities = target.get("capabilities")
    test_build = target.get("testBuild")
    if (not isinstance(capabilities, dict) or not isinstance(test_build, dict)
            or test_build.get("scenePath") != SCENE_PATH):
        fail("private iOS target lacks its fixed capability/test-build contract")
    udid = capabilities.get("appium:udid")
    platform_version = capabilities.get("appium:platformVersion")
    if (not isinstance(udid, str) or not udid or not isinstance(platform_version, str)
            or not re.fullmatch(r"[0-9]+(?:[.][0-9]+){0,2}", platform_version)
            or int(platform_version.partition(".")[0]) < 18):
        fail("private iOS target must retain an explicit physical iOS 18+ identity")
    if capabilities.get("appium:autoLaunch") not in {None, False}:
        fail("private iOS target must not auto-launch before controlled arguments are ready")
    forbidden = {
        "appium:xcodeConfigFile", "appium:xcodeOrgId", "appium:xcodeSigningId",
        "appium:keychainPath", "appium:keychainPassword",
    }
    if forbidden.intersection(capabilities):
        fail("private Fedora target contains Xcode-only signing capabilities")
    if not isinstance(receipt, dict) or set(receipt) != {
        "schemaVersion", "contract", "sourceRevision", "createdAt", "notAfter",
        "provenance", "overte", "wda", "toolchain",
    } or receipt.get("schemaVersion") != 1 or receipt.get("contract") not in {
        PROTECTED_RECEIPT, PERSONAL_RECEIPT, PREINSTALLED_RECEIPT,
    }:
        fail("private artifact receipt contract is invalid")
    overte = receipt["overte"]
    wda = receipt["wda"]
    suffix = ".xctrunner"
    if (not isinstance(overte, dict) or not isinstance(wda, dict)
            or not isinstance(overte.get("bundleId"), str)
            or not isinstance(wda.get("bundleId"), str)
            or not wda["bundleId"].endswith(suffix)):
        fail("verified WDA bundle does not have the XCTest runner suffix")
    preserved = (udid, platform_version, test_build["scenePath"])
    target["enabled"] = True
    target["appId"] = overte["bundleId"]
    target["artifactReceipt"] = str(receipt_path.resolve())
    preinstalled = receipt["contract"] == PREINSTALLED_RECEIPT
    target["artifactMode"] = "personal-team-preinstalled" if preinstalled else "signed-ipa"
    capabilities["appium:bundleId"] = overte["bundleId"]
    capabilities["appium:usePreinstalledWDA"] = True
    capabilities["appium:updatedWDABundleId"] = wda["bundleId"].removesuffix(suffix)
    capabilities["appium:autoLaunch"] = False
    if preinstalled:
        if (set(overte) != {"bundleId", "installed"}
                or set(wda) != {"bundleId", "xctestBundleId", "installed"}
                or overte["installed"] is not True or wda["installed"] is not True
                or wda["xctestBundleId"] != wda["bundleId"].removesuffix(suffix)):
            fail("preinstalled Personal-Team receipt app inventory is invalid")
        capabilities.pop("appium:app", None)
        capabilities.pop("appium:prebuiltWDAPath", None)
        capabilities["appium:enforceAppInstall"] = False
    else:
        if (set(overte) != {"path", "sha256", "bundleId"}
                or set(wda) != {
                    "ipaPath", "ipaSha256", "prebuiltPath", "prebuiltTreeSha256",
                    "bundleId"}):
            fail("signed IPA receipt inventory is invalid")
        capabilities["appium:app"] = overte["path"]
        capabilities["appium:prebuiltWDAPath"] = wda["prebuiltPath"]
        capabilities["appium:enforceAppInstall"] = False
    if preserved != (
        capabilities["appium:udid"], capabilities["appium:platformVersion"],
        test_build["scenePath"],
    ):
        fail("private target identity or fixed scene path changed during activation")
    secure_json(config_path, config)


def require_receipt_binding(receipt_path: Path, run: dict) -> dict:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("final iOS artifact receipt is unreadable")
    expected_provenance = {
        "repository": DEFAULT_REPOSITORY,
        "repositoryId": run["repository"]["id"],
        "workflow": WORKFLOW_PATH,
        "reusableWorkflow": ".github/workflows/ios-fedora-e2e-producer.yml",
        "ref": f"refs/heads/{PROTECTED_REF}",
        "runId": run["id"],
        "runAttempt": run["run_attempt"],
    }
    if (receipt.get("sourceRevision") != run["head_sha"]
            or receipt.get("provenance") != expected_provenance):
        fail("iOS artifact receipt does not match the protected workflow attempt")
    return receipt


def dispatch_inputs(arguments: argparse.Namespace) -> dict[str, str]:
    names = {
        "fedora_e2e_producer": "true",
        "qt_host_cache_key": arguments.qt_host_cache_key,
        "qt_ios_cache_key": arguments.qt_ios_cache_key,
        "qt_host_artifact_prefix": arguments.qt_host_artifact_prefix,
        "qt_ios_artifact_prefix": arguments.qt_ios_artifact_prefix,
        "overte_bundle_id": arguments.overte_bundle_id,
        "wda_bundle_id": arguments.wda_bundle_id,
    }
    expected = {
        "fedora_e2e_producer": r"true",
        "qt_host_cache_key": r"overte-qt-host-v2-[A-Za-z0-9._-]{1,190}-contract-[0-9a-f]{64}",
        "qt_ios_cache_key": r"overte-qt-ios-v2-[A-Za-z0-9._-]{1,190}-contract-[0-9a-f]{64}",
        "qt_host_artifact_prefix": r"overte-qt-host-checkpoint-v1-[0-9a-f]{32}",
        "qt_ios_artifact_prefix": r"overte-qt-ios-checkpoint-v1-[0-9a-f]{32}",
        "overte_bundle_id": r"[A-Za-z0-9][A-Za-z0-9.-]*[.]e2e",
        "wda_bundle_id": r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+",
    }
    if any(not re.fullmatch(expected[name], value) for name, value in names.items()):
        fail("protected producer input does not satisfy its fixed provenance namespace")
    if names["wda_bundle_id"].endswith(".xctrunner"):
        fail("WDA workflow input must be the Appium base bundle identifier")
    return names


def copy_private_input(source: Path, destination: Path, limit: int, label: str) -> None:
    if (not source.is_absolute() or has_symlink_component(source) or source.is_symlink()
            or not source.is_file() or inside_repository(source)):
        fail(f"{label} must be an absolute private regular file")
    metadata = source.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1 or metadata.st_mode & 0o077):
        fail(f"{label} must be owned mode-0600 private data")
    initial_size = metadata.st_size
    if not 0 < initial_size <= limit:
        fail(f"{label} size is invalid")
    initial_digest = sha256_file(source)
    total = 0
    try:
        with source.open("rb") as input_file, destination.open("xb") as output:
            while block := input_file.read(min(1024 * 1024, limit - total + 1)):
                total += len(block)
                if total > limit:
                    fail(f"{label} exceeded its copy limit")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        destination.chmod(0o600)
        if (total != initial_size or sha256_file(destination) != initial_digest
                or source.stat().st_size != initial_size
                or sha256_file(source) != initial_digest):
            fail(f"{label} changed during its private copy")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def run_personal_team_verifier(arguments: argparse.Namespace, root: Path,
                               receipt: Path, rcodesign: Path) -> None:
    result = subprocess.run([
        sys.executable, str(PERSONAL_TEAM_VERIFIER),
        "--unsigned-kit", str(root / "personal-team-e2e-kit.json"),
        "--attestation", str(root / "personal-team-signed-handoff.json"),
        "--overte-ipa", str(root / PERSONAL_OVERTE_IPA),
        "--wda-ipa", str(root / PERSONAL_WDA_IPA),
        "--receipt", str(receipt), "--rcodesign", str(rcodesign),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
       timeout=15 * 60, check=False)
    if result.returncode:
        fail("private Personal-Team IPA pair failed the Fedora verifier")


def run_local_import(arguments: argparse.Namespace) -> int:
    if (not arguments.destination.is_absolute()
            or arguments.target_config and not arguments.target_config.is_absolute()):
        fail("Personal-Team destination and target config must be absolute private paths")
    destination_root = arguments.destination.resolve()
    if has_symlink_component(arguments.destination) or destination_root == Path(
            destination_root.anchor) or inside_repository(destination_root):
        fail("destination must be a safe non-root private directory")
    private_directory(destination_root)
    security_tools = install_security_tools(destination_root / ".security-tools")
    temporary = Path(tempfile.mkdtemp(prefix=".personal-team-", dir=destination_root))
    final: Path | None = None
    moved = False
    try:
        for source, name, limit, label in (
            (arguments.unsigned_kit, "personal-team-e2e-kit.json", MAX_MANIFEST_BYTES,
             "unsigned kit manifest"),
            (arguments.attestation, "personal-team-signed-handoff.json", MAX_MANIFEST_BYTES,
             "Personal-Team attestation"),
            (arguments.overte_ipa, PERSONAL_OVERTE_IPA, MAX_IPA_BYTES,
             "signed Personal-Team Overte IPA"),
            (arguments.wda_ipa, PERSONAL_WDA_IPA, MAX_IPA_BYTES,
             "signed Personal-Team WDA IPA"),
        ):
            copy_private_input(source, temporary / name, limit, label)
        attestation_digest = sha256_file(
            temporary / "personal-team-signed-handoff.json"
        )
        final = destination_root / f"personal-team-{attestation_digest[:16]}"
        if final.exists() or final.is_symlink():
            fail("private destination for this Personal-Team handoff already exists")
        receipt = temporary / "personal-team-artifacts-receipt.json"
        run_personal_team_verifier(
            arguments, temporary, receipt, security_tools["rcodesign"]
        )
        temporary.replace(final)
        moved = True
        final_receipt = final / receipt.name
        final_receipt.unlink()
        shutil.rmtree(final / "WebDriverAgentRunner-Runner.app")
        run_personal_team_verifier(
            arguments, final, final_receipt, security_tools["rcodesign"]
        )
        if arguments.target_config:
            activate_target(
                arguments.target_config.resolve(), arguments.target_selector, final_receipt
            )
        print("PASS: private Personal-Team signed IPA handoff is verified and ready.")
        return 0
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        if moved and final is not None and final.exists():
            shutil.rmtree(final)
        raise


def validate_preinstalled_attestation(path: Path) -> tuple[dict, datetime]:
    if (not path.is_absolute() or has_symlink_component(path) or path.is_symlink()
            or not path.is_file() or not 0 < path.stat().st_size <= MAX_MANIFEST_BYTES):
        fail("preinstalled Personal-Team attestation must be a safe private file")
    metadata = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1 or metadata.st_mode & 0o077):
        fail("preinstalled Personal-Team attestation must have mode 0600")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("preinstalled Personal-Team attestation is unreadable")
    expected_keys = {
        "schemaVersion", "contract", "sourceRevision", "createdAt", "notAfter",
        "expectedBundleIdentifiers", "toolchain", "humanAttestation",
        "signingObservation", "unsignedKitManifestSha256",
    }
    bundles = {
        "overte": "org.overte.interface.e2e",
        "wdaRunner": "org.overte.WebDriverAgentRunner.xctrunner",
        "wdaXCTest": "org.overte.WebDriverAgentRunner",
    }
    toolchain = {
        "xcuitestDriver": "12.8.0", "remoteXpc": "5.15.3",
        "webdriverAgent": "16.8.0",
    }
    human = {
        "deviceObserved": True, "installedWithSideloadly": True,
        "fixedBundleIdentifiersConfirmed": True,
        "acceptedNoCryptographicByteBinding": True,
        "derivationBinding": "none-device-observed",
    }
    if (not isinstance(value, dict) or set(value) != expected_keys
            or value.get("schemaVersion") != 1
            or value.get("contract")
            != "overte-ios-personal-team-preinstalled-attestation-v1"
            or not isinstance(value.get("sourceRevision"), str)
            or not REVISION_RE.fullmatch(value["sourceRevision"])
            or not isinstance(value.get("unsignedKitManifestSha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["unsignedKitManifestSha256"])
            or value.get("expectedBundleIdentifiers") != bundles
            or value.get("toolchain") != toolchain
            or value.get("humanAttestation") != human):
        fail("preinstalled Personal-Team attestation contract is invalid")
    try:
        created = datetime.strptime(value["createdAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        not_after = datetime.strptime(value["notAfter"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (KeyError, TypeError, ValueError):
        fail("preinstalled Personal-Team attestation timestamps are invalid")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if created > now + timedelta(minutes=5) or not_after <= now \
            or not_after > created + timedelta(hours=1):
        fail("preinstalled Personal-Team attestation validity window is unsafe")
    observation = value.get("signingObservation")
    if observation is not None:
        expected_observation = {
            "teamIdentifier", "profileExpiration", "applicationIdentifiers",
        }
        applications = {
            "overte": lambda team: f"{team}.{bundles['overte']}",
            "wdaRunner": lambda team: f"{team}.{bundles['wdaRunner']}",
            "wdaXCTest": lambda team: f"{team}.{bundles['wdaXCTest']}",
        }
        if (not isinstance(observation, dict) or set(observation) != expected_observation
                or not isinstance(observation.get("teamIdentifier"), str)
                or not re.fullmatch(r"[A-Z0-9]{10}", observation["teamIdentifier"])
                or not isinstance(observation.get("applicationIdentifiers"), dict)):
            fail("preinstalled signing observation is invalid")
        team = observation["teamIdentifier"]
        if observation["applicationIdentifiers"] != {
                role: derive(team) for role, derive in applications.items()}:
            fail("preinstalled application identifiers do not match one Personal Team")
        try:
            profile_expiry = datetime.strptime(
                observation["profileExpiration"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            fail("preinstalled profile expiration is invalid")
        if profile_expiry < not_after or profile_expiry > created + timedelta(days=7):
            fail("preinstalled profile expiration is outside Personal-Team limits")
    return value, not_after


def target_udid(config_path: Path, selector: str) -> str:
    if (not config_path.is_absolute() or has_symlink_component(config_path)
            or not config_path.is_file() or inside_repository(config_path)
            or config_path.lstat().st_mode & 0o077):
        fail("private target configuration is unsafe")
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("private target configuration is unreadable")
    targets = value.get("targets") if isinstance(value, dict) else None
    matches = [item for item in targets or [] if isinstance(item, dict)
               and item.get("selector") == selector and item.get("platform") == "ios"]
    if len(matches) != 1 or not isinstance(matches[0].get("capabilities"), dict):
        fail("private selector does not identify exactly one iOS target")
    udid = matches[0]["capabilities"].get("appium:udid")
    if not isinstance(udid, str) or not 8 <= len(udid) <= 128 or any(
            character in udid for character in "\0\r\n"):
        fail("private iOS target UDID is invalid")
    return udid


def run_preinstalled(arguments: argparse.Namespace) -> int:
    if (not arguments.destination.is_absolute() or not arguments.target_config.is_absolute()
            or not arguments.service_runtime.is_absolute()):
        fail("preinstalled paths must be absolute")
    if arguments.service_runtime != PINNED_SERVICE_RUNTIME:
        fail("preinstalled mode requires the exact pinned immutable service runtime")
    attestation, not_after = validate_preinstalled_attestation(arguments.attestation)
    udid = target_udid(arguments.target_config, arguments.target_selector)
    wrapper = arguments.service_runtime / "remotexpc_tunnel.py"
    result = subprocess.run(
        [str(wrapper), "device-preflight", "--service-runtime",
         str(arguments.service_runtime)],
        input=json.dumps({"udid": udid}).encode("utf-8"), stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=65, check=False,
    )
    if result.returncode:
        fail("preinstalled iOS app device observation failed")
    destination_path = arguments.destination.resolve()
    if inside_repository(destination_path) or destination_path == Path(destination_path.anchor):
        fail("preinstalled receipt destination must be outside the repository")
    destination = private_directory(destination_path)
    digest = sha256_file(arguments.attestation)
    final = destination / f"personal-team-preinstalled-{digest[:16]}"
    if final.exists() or final.is_symlink():
        fail("private destination for this preinstalled observation already exists")
    temporary = Path(tempfile.mkdtemp(prefix=".preinstalled-", dir=destination))
    moved = False
    try:
        copy_private_input(
            arguments.attestation, temporary / "personal-team-preinstalled-attestation.json",
            MAX_MANIFEST_BYTES, "preinstalled Personal-Team attestation",
        )
        provenance = {
            "mode": "personal-team-preinstalled",
            "derivationBinding": "none-device-observed",
            "cryptographicByteBinding": False,
            "installationProxyValidated": True,
            "attestationSha256": digest,
            "unsignedKitContract": "overte-ios-personal-team-e2e-kit-v1",
            "unsignedKitManifestSha256": attestation["unsignedKitManifestSha256"],
            "attestationContract":
                "overte-ios-personal-team-preinstalled-attestation-v1",
            "signingObservation": attestation["signingObservation"],
        }
        receipt = temporary / "personal-team-preinstalled-receipt.json"
        secure_json(receipt, {
            "schemaVersion": 1, "contract": PREINSTALLED_RECEIPT,
            "sourceRevision": attestation["sourceRevision"],
            "createdAt": attestation["createdAt"],
            "notAfter": not_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "provenance": provenance,
            "overte": {"bundleId": "org.overte.interface.e2e", "installed": True},
            "wda": {
                "bundleId": "org.overte.WebDriverAgentRunner.xctrunner",
                "xctestBundleId": "org.overte.WebDriverAgentRunner", "installed": True,
            },
            "toolchain": attestation["toolchain"],
        })
        temporary.replace(final)
        moved = True
        final_receipt = final / receipt.name
        activate_target(
            arguments.target_config.resolve(), arguments.target_selector, final_receipt
        )
        print("PASS: preinstalled Personal-Team device observation is ready.")
        return 0
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        if moved and final.exists():
            shutil.rmtree(final)
        raise


def run(arguments: argparse.Namespace) -> int:
    if arguments.repository != DEFAULT_REPOSITORY:
        fail(f"repository must be the protected producer {DEFAULT_REPOSITORY}")
    if (not arguments.destination.is_absolute() or has_symlink_component(arguments.destination)
            or arguments.target_config and not arguments.target_config.is_absolute()):
        fail("destination must not be a symbolic link")
    destination_root = arguments.destination.resolve()
    if destination_root == Path(destination_root.anchor) or inside_repository(destination_root):
        fail("destination must be outside the repository and not a filesystem root")
    identity = private_age_identity()
    security_tools = install_security_tools(destination_root / ".security-tools")
    api = GitHubApi(arguments.repository, os.environ.get("OVERTE_GITHUB_TOKEN", ""))
    run_id = arguments.run_id or api.dispatch(dispatch_inputs(arguments))
    expected_attempt = arguments.run_attempt if arguments.run_id else 1
    print(f"Protected iOS producer run {run_id} attempt {expected_attempt} selected; waiting.")
    completed = wait_for_run(
        api, run_id, expected_attempt, arguments.timeout_seconds, arguments.poll_seconds
    )
    selected = select_artifacts(api.artifacts(run_id), completed)

    private_directory(destination_root)
    final = destination_root / f"run-{run_id}-attempt-{completed['run_attempt']}"
    if final.exists() or final.is_symlink():
        fail("private destination for this producer attempt already exists")
    temporary = Path(tempfile.mkdtemp(prefix=".ios-handoff-", dir=destination_root))
    moved = False
    try:
        extracted: dict[str, tuple[Path, Path]] = {}
        provenance: dict[str, dict] = {}
        for role in ("overte", "wda"):
            metadata = selected[role]
            archive_path = temporary / f"{role}.zip"
            api.download(metadata["archive_download_url"], archive_path)
            actual_digest = sha256_file(archive_path)
            if actual_digest != metadata["digest"].removeprefix("sha256:"):
                fail(f"{role} workflow artifact failed its GitHub SHA-256")
            encrypted_name = metadata["name"] + ".zip.age"
            encrypted = extract_encrypted_payload(
                archive_path, temporary, encrypted_name, role
            )
            archive_path.unlink()
            decrypted = temporary / f"{role}-decrypted.zip"
            decrypt_payload(security_tools["age"], identity, encrypted, decrypted)
            encrypted.unlink()
            extracted[role] = safe_extract(decrypted, temporary / role, role)
            decrypted.unlink()
            provenance[role] = {
                "artifactId": metadata["id"],
                "artifactName": metadata["name"],
                "archiveSha256": actual_digest,
            }

        receipt = temporary / "fedora-artifacts-receipt.json"
        command = [
            sys.executable, str(VERIFIER),
            "--overte-manifest", str(extracted["overte"][1]),
            "--overte-ipa", str(extracted["overte"][0]),
            "--wda-manifest", str(extracted["wda"][1]),
            "--wda-ipa", str(extracted["wda"][0]),
            "--receipt", str(receipt),
            "--rcodesign", str(security_tools["rcodesign"]),
            "--expected-repository", arguments.repository,
            "--expected-repository-id", str(completed["repository"]["id"]),
            "--expected-run-id", str(run_id),
            "--expected-run-attempt", str(completed["run_attempt"]),
        ]
        verification = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, check=False)
        if verification.returncode:
            fail("downloaded iOS artifact pair failed the Fedora verifier")
        handoff = {
            "schemaVersion": 1,
            "contract": "overte-ios-fedora-github-handoff-v1",
            "repository": arguments.repository,
            "repositoryId": completed["repository"]["id"],
            "workflow": WORKFLOW_PATH,
            "reusableWorkflow": ".github/workflows/ios-fedora-e2e-producer.yml",
            "protectedRef": PROTECTED_REF,
            "runId": run_id,
            "runAttempt": completed["run_attempt"],
            "sourceRevision": completed["head_sha"],
            "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "artifacts": provenance,
        }
        secure_json(temporary / "github-handoff.json", handoff)
        temporary.replace(final)
        moved = True
        final_receipt = final / receipt.name
        # The verifier ran before the atomic rename, so bind receipt paths to the
        # immutable final location and re-run it there.
        final_receipt.unlink()
        shutil.rmtree(final / "WebDriverAgentRunner-Runner.app")
        verification = subprocess.run([
            sys.executable, str(VERIFIER),
            "--overte-manifest", str(final / "overte" / extracted["overte"][1].name),
            "--overte-ipa", str(final / "overte" / extracted["overte"][0].name),
            "--wda-manifest", str(final / "wda" / extracted["wda"][1].name),
            "--wda-ipa", str(final / "wda" / extracted["wda"][0].name),
            "--receipt", str(final_receipt),
            "--rcodesign", str(security_tools["rcodesign"]),
            "--expected-repository", arguments.repository,
            "--expected-repository-id", str(completed["repository"]["id"]),
            "--expected-run-id", str(run_id),
            "--expected-run-attempt", str(completed["run_attempt"]),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if verification.returncode:
            fail("final private iOS artifact pair failed receipt binding")
        require_receipt_binding(final_receipt, completed)
        if arguments.target_config:
            if has_symlink_component(arguments.target_config):
                fail("target configuration must not be a symbolic link")
            activate_target(arguments.target_config.resolve(), arguments.target_selector, final_receipt)
        print(f"PASS: protected iOS producer run {run_id} is verified and ready on Fedora.")
        return 0
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        if moved and final.exists():
            shutil.rmtree(final)
        raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--repository", default=DEFAULT_REPOSITORY)
    value.add_argument("--run-id", type=int)
    value.add_argument("--run-attempt", type=int)
    value.add_argument("--destination", type=Path, required=True)
    value.add_argument("--target-config", type=Path)
    value.add_argument("--target-selector", default="",
                       help="prefer OVERTE_DEVICE_TARGET_SELECTOR to keep this out of process listings")
    value.add_argument("--timeout-seconds", type=int, default=8 * 60 * 60)
    value.add_argument("--poll-seconds", type=int, default=20)
    value.add_argument("--qt-host-cache-key", default="")
    value.add_argument("--qt-ios-cache-key", default="")
    value.add_argument("--qt-host-artifact-prefix", default="")
    value.add_argument("--qt-ios-artifact-prefix", default="")
    value.add_argument("--overte-bundle-id", default="org.overte.interface.e2e")
    value.add_argument("--wda-bundle-id", default="org.overte.WebDriverAgentRunner")
    return value


def local_import_parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Verify and activate private Personal-Team signed IPA exports."
    )
    value.add_argument("--unsigned-kit", type=Path, required=True)
    value.add_argument("--attestation", type=Path, required=True)
    value.add_argument("--overte-ipa", type=Path, required=True)
    value.add_argument("--wda-ipa", type=Path, required=True)
    value.add_argument("--destination", type=Path, required=True)
    value.add_argument("--target-config", type=Path)
    value.add_argument("--target-selector", default="")
    return value


def preinstalled_parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Observe and activate already installed Personal-Team apps."
    )
    value.add_argument("--attestation", type=Path, required=True)
    value.add_argument("--destination", type=Path, required=True)
    value.add_argument("--target-config", type=Path, required=True)
    value.add_argument("--target-selector", default="")
    value.add_argument(
        "--service-runtime", type=Path,
        default=PINNED_SERVICE_RUNTIME,
    )
    return value


def main() -> int:
    try:
        raw_arguments = sys.argv[1:]
        action = "github"
        if raw_arguments and raw_arguments[0] in {"local-import", "personal-team-preinstalled"}:
            action = raw_arguments.pop(0)
        if action == "local-import":
            arguments = local_import_parser().parse_args(raw_arguments)
        elif action == "personal-team-preinstalled":
            arguments = preinstalled_parser().parse_args(raw_arguments)
        else:
            arguments = parser().parse_args(raw_arguments)
        if not arguments.target_selector:
            arguments.target_selector = os.environ.get("OVERTE_DEVICE_TARGET_SELECTOR", "")
        if action == "local-import":
            if bool(arguments.target_config) != bool(arguments.target_selector):
                fail("target config and private target selector must be supplied together")
            return run_local_import(arguments)
        if action == "personal-team-preinstalled":
            if not arguments.target_selector:
                fail("preinstalled mode requires the private target selector")
            return run_preinstalled(arguments)
        if arguments.run_id is not None and arguments.run_id <= 0:
            fail("run ID must be positive")
        if bool(arguments.run_id) != bool(arguments.run_attempt):
            fail("explicit run ID and positive run attempt must be supplied together")
        if arguments.run_attempt is not None and arguments.run_attempt <= 0:
            fail("run attempt must be positive")
        if arguments.timeout_seconds <= 0 or not 1 <= arguments.poll_seconds <= 300:
            fail("timeout and polling interval must be positive and bounded")
        if bool(arguments.target_config) != bool(arguments.target_selector):
            fail("target config and private target selector must be supplied together")
        return run(arguments)
    except (HandoffError, OSError, json.JSONDecodeError, KeyError,
            subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
