#!/usr/bin/env python3
"""Dispatch, download, verify, and activate the signed iOS Fedora handoff."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
VERIFIER = Path(__file__).with_name("verify_fedora_artifacts.py")
IOS_ROOT = Path(__file__).resolve().parent
if str(IOS_ROOT) not in sys.path:
    sys.path.insert(0, str(IOS_ROOT))
from security_tools import install as install_security_tools  # noqa: E402
API_VERSION = "2026-03-10"
DEFAULT_REPOSITORY = "noah-be/overte"
WORKFLOW = "ios-fedora-e2e-producer.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW}"
PROTECTED_REF = "apple-ios"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OVERTE_IPA_RE = re.compile(r"^[0-9]{4,}-OverteIOSClient-Release-device-signed[.]ipa$")
WDA_IPA = "WebDriverAgentRunner-Runner-16.8.0-signed.ipa"
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 8


class HandoffError(ValueError):
    """The authenticated Actions handoff failed closed."""


def fail(message: str) -> "NoReturn":
    raise HandoffError(message)


def private_directory(path: Path) -> Path:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        fail("private handoff path must be a real directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(stat.S_IRWXU)
    return path


def secure_json(path: Path, value: dict) -> None:
    private_directory(path.parent)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if os.name != "nt":
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary.replace(path)


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
            {"ref": PROTECTED_REF, "inputs": inputs},
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
                    if total > MAX_DOWNLOAD_BYTES:
                        fail("GitHub artifact exceeded the download safety limit")
                    output.write(block)
        except urllib.error.HTTPError as error:
            fail(f"GitHub artifact download failed with HTTP {error.code}")
        except urllib.error.URLError as error:
            fail(f"GitHub artifact download failed: {type(error.reason).__name__}")


def verify_run(run: dict, run_id: int, *, require_complete: bool) -> dict:
    path = run.get("path")
    repository = run.get("repository")
    head_repository = run.get("head_repository")
    if (
        run.get("id") != run_id
        or run.get("event") != "workflow_dispatch"
        or not isinstance(path, str)
        or not path.startswith(WORKFLOW_PATH + "@")
        or run.get("head_branch") != PROTECTED_REF
        or not isinstance(run.get("head_sha"), str)
        or not REVISION_RE.fullmatch(run["head_sha"])
        or not isinstance(repository, dict)
        or repository.get("full_name") != DEFAULT_REPOSITORY
        or not isinstance(head_repository, dict)
        or head_repository.get("full_name") != DEFAULT_REPOSITORY
        or not isinstance(run.get("run_attempt"), int)
        or run["run_attempt"] <= 0
    ):
        fail("workflow run is outside the protected iOS producer boundary")
    if require_complete and (run.get("status") != "completed" or run.get("conclusion") != "success"):
        fail("protected iOS producer did not complete successfully")
    return run


def wait_for_run(api: GitHubApi, run_id: int, timeout_seconds: int, poll_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        run = verify_run(api.run(run_id), run_id, require_complete=False)
        if run.get("status") == "completed":
            return verify_run(run, run_id, require_complete=True)
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
            or workflow_run.get("head_branch") != PROTECTED_REF
            or workflow_run.get("head_sha") != run["head_sha"]
        ):
            fail(f"{role} artifact provenance is invalid")
        selected[role] = item
    return selected


def safe_extract(archive_path: Path, destination: Path, role: str) -> tuple[Path, Path]:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile):
        fail(f"{role} workflow artifact is not a valid ZIP")
    with archive:
        entries = archive.infolist()
        if len(entries) != 2 or len(entries) > MAX_ARCHIVE_ENTRIES:
            fail(f"{role} workflow artifact must contain exactly two files")
        names: set[str] = set()
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
            if entry.file_size <= 0 or entry.file_size > MAX_DOWNLOAD_BYTES:
                fail(f"{role} workflow artifact entry size is invalid")
            names.add(name)
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
            with archive.open(entry) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            if os.name != "nt":
                target.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return destination / ipa_name, destination / manifest_names[0]


def extract_encrypted_payload(archive_path: Path, destination: Path,
                              expected_name: str, role: str) -> Path:
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
            or not 0 < entry.file_size <= MAX_DOWNLOAD_BYTES
        ):
            fail(f"{role} encrypted workflow payload is unsafe")
        target = destination / expected_name
        with archive.open(entry) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        if os.name != "nt":
            target.chmod(0o600)
        return target


def private_age_identity() -> Path:
    value = os.environ.get("OVERTE_IOS_AGE_IDENTITY_FILE", "")
    path = Path(value).expanduser()
    if (not value or has_symlink_component(path) or not path.is_absolute()
            or not path.is_file()):
        fail("OVERTE_IOS_AGE_IDENTITY_FILE must name an absolute private age identity file")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        fail("age identity file must not be accessible to group or other users")
    return path


def decrypt_payload(age: Path, identity: Path, encrypted: Path, destination: Path) -> None:
    result = subprocess.run(
        [str(age), "--decrypt", "--identity", str(identity),
         "--output", str(destination), str(encrypted)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=15 * 60, check=False,
    )
    if result.returncode or not destination.is_file():
        fail("signed iOS workflow payload failed authenticated age decryption")
    if destination.stat().st_size > MAX_DOWNLOAD_BYTES:
        destination.unlink()
        fail("decrypted iOS workflow payload exceeds the safety limit")
    if os.name != "nt":
        destination.chmod(0o600)


def activate_target(config_path: Path, selector: str, receipt_path: Path) -> None:
    if (has_symlink_component(config_path) or not config_path.is_absolute()
            or not config_path.is_file()):
        fail("iOS target configuration must be an existing absolute private file")
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
    if not isinstance(capabilities, dict):
        fail("private iOS target has no capabilities object")
    overte = receipt["overte"]
    wda = receipt["wda"]
    suffix = ".xctrunner"
    if not wda["bundleId"].endswith(suffix):
        fail("verified WDA bundle does not have the XCTest runner suffix")
    target["appId"] = overte["bundleId"]
    target["artifactReceipt"] = str(receipt_path.resolve())
    capabilities["appium:bundleId"] = overte["bundleId"]
    capabilities["appium:app"] = overte["path"]
    capabilities["appium:prebuiltWDAPath"] = wda["path"]
    capabilities["appium:updatedWDABundleId"] = wda["bundleId"].removesuffix(suffix)
    secure_json(config_path, config)


def require_receipt_revision(receipt_path: Path, expected_revision: str) -> dict:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("final iOS artifact receipt is unreadable")
    if receipt.get("sourceRevision") != expected_revision:
        fail("iOS artifact source revision does not match the protected workflow run")
    return receipt


def dispatch_inputs(arguments: argparse.Namespace) -> dict[str, str]:
    names = {
        "qt_host_cache_key": arguments.qt_host_cache_key,
        "qt_ios_cache_key": arguments.qt_ios_cache_key,
        "qt_host_artifact_prefix": arguments.qt_host_artifact_prefix,
        "qt_ios_artifact_prefix": arguments.qt_ios_artifact_prefix,
        "overte_bundle_id": arguments.overte_bundle_id,
        "wda_bundle_id": arguments.wda_bundle_id,
    }
    expected = {
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


def run(arguments: argparse.Namespace) -> int:
    if arguments.repository != DEFAULT_REPOSITORY:
        fail(f"repository must be the protected producer {DEFAULT_REPOSITORY}")
    if has_symlink_component(arguments.destination):
        fail("destination must not be a symbolic link")
    destination_root = arguments.destination.resolve()
    if destination_root == Path(destination_root.anchor):
        fail("destination must not be a filesystem root")
    identity = private_age_identity()
    security_tools = install_security_tools(destination_root / ".security-tools")
    api = GitHubApi(arguments.repository, os.environ.get("OVERTE_GITHUB_TOKEN", ""))
    run_id = arguments.run_id or api.dispatch(dispatch_inputs(arguments))
    print(f"Protected iOS producer run {run_id} selected; waiting for completion.")
    completed = wait_for_run(api, run_id, arguments.timeout_seconds, arguments.poll_seconds)
    selected = select_artifacts(api.artifacts(run_id), completed)

    private_directory(destination_root)
    final = destination_root / f"run-{run_id}-attempt-{completed['run_attempt']}"
    if final.exists():
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
        ]
        verification = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, check=False)
        if verification.returncode:
            fail("downloaded iOS artifact pair failed the Fedora verifier")
        handoff = {
            "schemaVersion": 1,
            "contract": "overte-ios-fedora-github-handoff-v1",
            "repository": arguments.repository,
            "workflow": WORKFLOW_PATH,
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
        verification = subprocess.run([
            sys.executable, str(VERIFIER),
            "--overte-manifest", str(final / "overte" / extracted["overte"][1].name),
            "--overte-ipa", str(final / "overte" / extracted["overte"][0].name),
            "--wda-manifest", str(final / "wda" / extracted["wda"][1].name),
            "--wda-ipa", str(final / "wda" / extracted["wda"][0].name),
            "--receipt", str(final_receipt),
            "--rcodesign", str(security_tools["rcodesign"]),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if verification.returncode:
            fail("final private iOS artifact pair failed receipt binding")
        require_receipt_revision(final_receipt, completed["head_sha"])
        if arguments.target_config:
            if has_symlink_component(arguments.target_config):
                fail("target configuration must not be a symbolic link")
            activate_target(arguments.target_config.resolve(), arguments.target_selector, final_receipt)
        print(f"PASS: protected iOS producer run {run_id} is verified and ready on Fedora.")
        return 0
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        if moved and final.exists():
            shutil.rmtree(final)
        raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--repository", default=DEFAULT_REPOSITORY)
    value.add_argument("--run-id", type=int)
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


def main() -> int:
    try:
        arguments = parser().parse_args()
        if not arguments.target_selector:
            arguments.target_selector = os.environ.get("OVERTE_DEVICE_TARGET_SELECTOR", "")
        if arguments.run_id is not None and arguments.run_id <= 0:
            fail("run ID must be positive")
        if arguments.timeout_seconds <= 0 or not 1 <= arguments.poll_seconds <= 300:
            fail("timeout and polling interval must be positive and bounded")
        if bool(arguments.target_config) != bool(arguments.target_selector):
            fail("target config and private target selector must be supplied together")
        return run(arguments)
    except (HandoffError, OSError, json.JSONDecodeError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
