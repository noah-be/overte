#!/usr/bin/env python3
"""Offline-sign the fixed unsigned WDA kit with one Personal-Team profile."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import resource
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
LOCK_FILE = Path(__file__).with_name("toolchain.lock.json")
RESIGNER_VERSION = "v0.3.1"
RESIGNER_VERSION_OUTPUT = f"resigner version {RESIGNER_VERSION}"
WDA_VERSION = "16.8.0"
XCUITEST_DRIVER_VERSION = "12.8.0"
WDA_VERSION_KEY = "OverteE2EWebDriverAgentVersion"
XCUITEST_VERSION_KEY = "OverteE2EXCUITestDriverVersion"
SOURCE_BUNDLE_IDS = {
    "runner": "org.overte.WebDriverAgentRunner.xctrunner",
    "xctest": "org.overte.WebDriverAgentRunner",
    "framework": "com.facebook.WebDriverAgentLib",
}
EXPECTED_EXECUTABLES = {
    "runner": "WebDriverAgentRunner-Runner",
    "xctest": "WebDriverAgentRunner",
    "framework": "WebDriverAgentLib",
}
WDA_APP = "WebDriverAgentRunner-Runner.app"
WDA_XCTEST = "PlugIns/WebDriverAgentRunner.xctest"
WDA_FRAMEWORK = f"{WDA_XCTEST}/Frameworks/WebDriverAgentLib.framework"
TEAM_RE = re.compile(r"[A-Z0-9]{10}")
UDID_RE = re.compile(r"(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f-]{16,55})")
BUNDLE_RE = re.compile(
    r"(?=.{3,255}\Z)[A-Za-z0-9][A-Za-z0-9-]*"
    r"(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+"
)
KIT_CONTRACT = "overte-ios-personal-team-e2e-kit-v3"
KIT_WDA_NAME = "WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa"
APPLE_ROOT_CA_PEM_SHA256 = (
    "f476b5c8ebe6468094981fb6a986e3d930fd020f6f379248000395a1a854c125"
)
APPLE_ROOT_CA_DER_SHA256 = (
    "b0b1730ecbc7ff4505142c49f1295e6eda6bcaed7e2c68c5be91b5a11001f024"
)
MAX_IPA_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 8192
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
MAX_PLIST_BYTES = 4 * 1024 * 1024
MAX_PROFILE_BYTES = 4 * 1024 * 1024
MAX_PASSWORD_BYTES = 4096
MAX_JSON_BYTES = 1024 * 1024
MAX_CERTIFICATE_BYTES = 64 * 1024
MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024
MAX_PROCESS_LOG_BYTES = 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 300
PERSONAL_TEAM_PROFILE_LIFETIME = timedelta(days=7)
PROFILE_CLOCK_TOLERANCE = timedelta(minutes=5)
RCODESIGN_BER_DIAGNOSTIC = (
    b"Error: error with plist DER encoding: Error Kind: Wrapped codec-specific "
    b"decode error\nCodec: BER\n\n"
)


class SigningError(RuntimeError):
    """The offline Personal-Team signing boundary failed closed."""


def fail(message: str) -> "NoReturn":
    raise SigningError(message)


def inside_repository(path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(REPOSITORY_ROOT)
        return True
    except ValueError:
        return False


def has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
        if not current.exists():
            break
    return False


def normalized_absolute(path: Path, label: str, *, must_exist: bool) -> Path:
    if not path.is_absolute() or path != path.resolve(strict=False):
        fail(f"{label} must be a normalized absolute path")
    if inside_repository(path):
        fail(f"{label} must remain outside the repository")
    if has_symlink_component(path):
        fail(f"{label} must not traverse symbolic links")
    if must_exist and not path.exists():
        fail(f"{label} is unavailable")
    return path


def require_safe_ancestry(directory: Path, label: str) -> None:
    """Reject ancestors another local user could replace or redirect."""
    allowed_owners = {0, os.geteuid()}
    current = directory
    while True:
        try:
            metadata = current.lstat()
        except OSError:
            fail(f"{label} has an unavailable ancestor")
        mode = stat.S_IMODE(metadata.st_mode)
        sticky_root = (
            metadata.st_uid == 0 and bool(metadata.st_mode & stat.S_ISVTX)
        )
        if (not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in allowed_owners
                or (mode & 0o022 and not sticky_root)):
            fail(f"{label} must have protected root/current-user ancestry")
        if current == current.parent:
            break
        current = current.parent


def require_private_directory(path: Path, label: str) -> Path:
    path = normalized_absolute(path, label, must_exist=True)
    require_safe_ancestry(path.parent, label)
    metadata = path.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        fail(f"{label} must be an owned mode-0700 directory")
    return path


def require_private_file(path: Path, label: str, maximum: int) -> Path:
    path = normalized_absolute(path, label, must_exist=True)
    require_private_directory(path.parent, f"{label} directory")
    metadata = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 0 < metadata.st_size <= maximum):
        fail(f"{label} must be an owned singly-linked mode-0600 regular file")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_pinned_tool(path: Path, name: str) -> Path:
    path = normalized_absolute(path, name, must_exist=True)
    require_safe_ancestry(path.parent, name)
    metadata = path.lstat()
    if (path.name != name or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1 or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_mode & 0o022 or not os.access(path, os.X_OK)):
        fail(f"{name} must be a protected executable named {name}")
    try:
        lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        expected = lock["appium"]["iosSecurity"][name]["executableSha256"]
    except (OSError, KeyError, json.JSONDecodeError):
        fail("iOS security-tool lock is unreadable")
    if (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or sha256_file(path) != expected):
        fail(f"{name} executable failed its pinned SHA-256")
    return path


def require_apple_root(path: Path) -> Path:
    path = normalized_absolute(path, "Apple Root CA PEM", must_exist=True)
    require_safe_ancestry(path.parent, "Apple Root CA PEM")
    metadata = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
            or not 0 < metadata.st_size <= MAX_CERTIFICATE_BYTES
            or sha256_file(path) != APPLE_ROOT_CA_PEM_SHA256):
        fail("Apple Root CA PEM failed its exact public trust-anchor pin")
    return path


def validate_paths(arguments: argparse.Namespace) -> None:
    require_private_file(arguments.unsigned_wda_ipa, "unsigned WDA IPA", MAX_IPA_BYTES)
    require_private_file(
        arguments.unsigned_kit_manifest, "unsigned kit manifest", MAX_JSON_BYTES
    )
    require_private_file(arguments.p12_file, "Personal-Team P12", MAX_PROFILE_BYTES)
    require_private_file(
        arguments.p12_password_file, "P12 password file", MAX_PASSWORD_BYTES
    )
    require_private_file(arguments.profile_file, "WDA profile", MAX_PROFILE_BYTES)
    require_private_file(arguments.device_udid_file, "device UDID file", 256)
    require_private_directory(arguments.profile_file.parent, "WDA profile directory")
    require_pinned_tool(arguments.resigner, "resigner")
    require_pinned_tool(arguments.rcodesign, "rcodesign")
    require_apple_root(arguments.apple_root_ca_pem)
    output = normalized_absolute(arguments.output_ipa, "signed WDA output", must_exist=False)
    require_private_directory(output.parent, "signed WDA output directory")
    if output.exists():
        fail("signed WDA output must not already exist")
    if output == arguments.unsigned_wda_ipa:
        fail("signed WDA output must differ from the unsigned input")
    inputs = {
        arguments.unsigned_wda_ipa,
        arguments.unsigned_kit_manifest,
        arguments.p12_file,
        arguments.p12_password_file,
        arguments.profile_file,
        arguments.device_udid_file,
    }
    if len(inputs) != 6:
        fail("private signing inputs must be six distinct files")


def read_password(path: Path) -> str:
    try:
        value = path.read_bytes()
    except OSError:
        fail("P12 password file is unreadable")
    if value.endswith(b"\r\n"):
        value = value[:-2]
    elif value.endswith(b"\n"):
        value = value[:-1]
    if not value or b"\x00" in value or b"\r" in value or b"\n" in value:
        fail("P12 password file must contain exactly one non-empty line")
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        fail("P12 password must be UTF-8")


def read_device_udid(path: Path) -> str:
    try:
        value = path.read_text(encoding="ascii")
    except (OSError, UnicodeError):
        fail("device UDID file is unreadable")
    value = value.removesuffix("\n")
    if value.endswith("\r"):
        value = value[:-1]
    if not UDID_RE.fullmatch(value):
        fail("device UDID file must contain exactly one physical-device identifier")
    return value


def validate_kit_manifest(path: Path, ipa: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("unsigned kit manifest is unreadable")
    required_keys = {
        "schemaVersion", "contract", "sourceRevision", "createdAt", "provenance",
        "overteArtifactReuse", "xcuitestDriverVersion", "webDriverAgentVersion",
        "webDriverAgentCredentialFreeSigning", "desiredBundleIdentifiers",
        "humanSigningBoundary", "upstream", "artifacts",
    }
    if (ipa.name != KIT_WDA_NAME
            or not isinstance(value, dict) or set(value) != required_keys
            or value.get("schemaVersion") != 1
            or value.get("contract") != KIT_CONTRACT
            or value.get("xcuitestDriverVersion") != XCUITEST_DRIVER_VERSION
            or value.get("webDriverAgentVersion") != WDA_VERSION
            or not isinstance(value.get("sourceRevision"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", value["sourceRevision"])):
        fail("unsigned kit manifest violates its exact v3 contract")
    if value.get("webDriverAgentCredentialFreeSigning") != {
        "nestedBundle": WDA_XCTEST,
        "method": "unsigned-requires-recursive-personal-team-signing",
        "outerRunnerBundleCodeResourcesPresent": False,
        "nestedBundleCodeResourcesPresent": False,
        "outerRunnerProvisioned": False,
    } or value.get("desiredBundleIdentifiers") != {
        "overte": "org.overte.interface.e2e",
        "wdaRunner": SOURCE_BUNDLE_IDS["runner"],
        "wdaXCTest": SOURCE_BUNDLE_IDS["xctest"],
    }:
        fail("unsigned kit manifest differs from the credential-free WDA contract")
    if value.get("humanSigningBoundary") != {
        "method": "manual-sideloadly-personal-team",
        "derivationBinding": "human-verified",
        "signedBytesDerivableFromUnsignedKit": False,
        "maximumProfileLifetimeDays": 7,
    }:
        fail("unsigned kit manifest lacks its declared human signing boundary")
    upstream = value.get("upstream")
    if (not isinstance(upstream, dict) or set(upstream) != {
            "webDriverAgentUrl", "webDriverAgentSha256"}
            or upstream.get("webDriverAgentUrl") !=
            "https://github.com/appium/WebDriverAgent/releases/download/v16.8.0/"
            "WebDriverAgentRunner-Runner.zip"
            or upstream.get("webDriverAgentSha256") !=
            "38ec705d6fa2c7825513adbc9406d4fda5d6a084a8d3980ceff9a265e62f9623"):
        fail("unsigned kit manifest has unexpected WDA upstream provenance")
    provenance = value.get("provenance")
    if (not isinstance(provenance, dict) or set(provenance) != {
            "repository", "repositoryId", "workflow", "reusableWorkflow", "ref",
            "runId", "runAttempt"}
            or provenance.get("repository") != "noah-be/overte"
            or provenance.get("workflow") != ".github/workflows/ios-bootstrap.yml"
            or provenance.get("reusableWorkflow") !=
            ".github/workflows/ios-personal-team-e2e-kit.yml"
            or provenance.get("ref") != "refs/heads/apple-ios"
            or any(not isinstance(provenance.get(field), int)
                   or isinstance(provenance[field], bool) or provenance[field] <= 0
                   for field in ("repositoryId", "runId", "runAttempt"))):
        fail("unsigned kit manifest producer provenance is invalid")
    artifacts = value.get("artifacts")
    wda = artifacts.get("webDriverAgent") if isinstance(artifacts, dict) else None
    if (not isinstance(artifacts, dict) or set(artifacts) != {
            "overte", "webDriverAgent"} or not isinstance(wda, dict)
            or set(wda) != {"name", "sha256", "size"}
            or wda.get("name") != KIT_WDA_NAME
            or wda.get("sha256") != sha256_file(ipa)
            or not isinstance(wda.get("size"), int)
            or isinstance(wda["size"], bool) or wda["size"] != ipa.stat().st_size):
        fail("unsigned WDA IPA is not SHA-256/size-bound to its kit manifest")
    return value


def safe_member_name(name: str) -> PurePosixPath:
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        fail("WDA IPA contains an unsafe member name")
    path = PurePosixPath(name.rstrip("/"))
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        fail("WDA IPA contains an unsafe member path")
    return path


def inspect_archive(archive: zipfile.ZipFile) -> tuple[list[zipfile.ZipInfo], set[str]]:
    entries = archive.infolist()
    if not entries or len(entries) > MAX_ARCHIVE_ENTRIES:
        fail("WDA IPA entry count is invalid")
    names: set[str] = set()
    total = 0
    for entry in entries:
        name = str(safe_member_name(entry.filename))
        if name in names:
            fail("WDA IPA contains duplicate members")
        names.add(name)
        mode = entry.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if (file_type == stat.S_IFLNK or entry.flag_bits & 1
                or entry.file_size < 0 or entry.file_size > MAX_MEMBER_BYTES):
            fail("WDA IPA contains an unsafe member")
        if entry.is_dir():
            if file_type not in {0, stat.S_IFDIR}:
                fail("WDA IPA contains an unsafe directory")
        else:
            if file_type not in {0, stat.S_IFREG}:
                fail("WDA IPA contains a non-regular member")
            if entry.file_size and entry.compress_size <= 0:
                fail("WDA IPA contains invalid compressed metadata")
            if (entry.file_size > 1024 * 1024
                    and entry.file_size > entry.compress_size * MAX_COMPRESSION_RATIO):
                fail("WDA IPA exceeds the compression-ratio limit")
        total += entry.file_size
        if total > MAX_EXPANDED_BYTES:
            fail("WDA IPA expands beyond the size limit")
    return entries, names


def read_member(archive: zipfile.ZipFile, name: str, maximum: int, label: str) -> bytes:
    try:
        entry = archive.getinfo(name)
    except KeyError:
        fail(f"WDA IPA lacks {label}")
    if entry.is_dir() or not 0 < entry.file_size <= maximum:
        fail(f"WDA IPA {label} size is invalid")
    with archive.open(entry) as source:
        value = source.read(maximum + 1)
    if len(value) != entry.file_size or len(value) > maximum:
        fail(f"WDA IPA {label} is truncated or oversized")
    return value


def read_plist(archive: zipfile.ZipFile, name: str, label: str) -> dict:
    try:
        value = plistlib.loads(read_member(archive, name, MAX_PLIST_BYTES, label))
    except (ValueError, plistlib.InvalidFileException):
        fail(f"WDA IPA {label} is not a plist")
    if not isinstance(value, dict):
        fail(f"WDA IPA {label} root is invalid")
    return value


def validate_bundle_plist(value: dict, expected_id: str, package: str, label: str,
                          expected_executable: str) -> str:
    executable = value.get("CFBundleExecutable")
    if (value.get("CFBundleIdentifier") != expected_id
            or value.get("CFBundlePackageType") != package
            or executable != expected_executable
            or PurePosixPath(str(executable)).name != executable):
        fail(f"WDA {label} bundle contract is invalid")
    return executable


def inspect_unsigned_wda(path: Path) -> None:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        fail("unsigned WDA input is not a valid IPA")
    with archive:
        _entries, names = inspect_archive(archive)
        root = f"Payload/{WDA_APP}"
        if any(name not in {"Payload", root} and not name.startswith(root + "/")
               for name in names):
            fail("unsigned WDA IPA contains content outside its fixed application")
        runner = read_plist(archive, f"{root}/Info.plist", "runner Info.plist")
        xctest = read_plist(
            archive, f"{root}/{WDA_XCTEST}/Info.plist", "XCTest Info.plist"
        )
        framework = read_plist(
            archive, f"{root}/{WDA_FRAMEWORK}/Info.plist", "framework Info.plist"
        )
        runner_executable = validate_bundle_plist(
            runner, SOURCE_BUNDLE_IDS["runner"], "APPL", "runner",
            EXPECTED_EXECUTABLES["runner"],
        )
        xctest_executable = validate_bundle_plist(
            xctest, SOURCE_BUNDLE_IDS["xctest"], "BNDL", "XCTest",
            EXPECTED_EXECUTABLES["xctest"],
        )
        framework_executable = validate_bundle_plist(
            framework, SOURCE_BUNDLE_IDS["framework"], "FMWK", "framework",
            EXPECTED_EXECUTABLES["framework"],
        )
        executables = {
            f"{root}/{runner_executable}",
            f"{root}/{WDA_XCTEST}/{xctest_executable}",
            f"{root}/{WDA_FRAMEWORK}/{framework_executable}",
        }
        if not executables.issubset(names):
            fail("unsigned WDA IPA lacks a required executable")
        for executable in executables:
            read_member(
                archive, executable, MAX_EXECUTABLE_BYTES,
                "fixed runner/XCTest/framework executable",
            )
        if (runner.get(WDA_VERSION_KEY) != WDA_VERSION
                or runner.get(XCUITEST_VERSION_KEY) != XCUITEST_DRIVER_VERSION):
            fail("unsigned WDA IPA differs from the pinned WDA/XCUITest pair")
        if any("_CodeSignature" in PurePosixPath(name).parts
               or PurePosixPath(name).name in {
                   "embedded.mobileprovision", "embedded.provisionprofile"
               } for name in names):
            fail("unsigned WDA IPA unexpectedly contains signing material")


def _child_limits() -> None:
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (MAX_IPA_BYTES, MAX_IPA_BYTES)
    )


def kill_process_group_and_reap(process: subprocess.Popen) -> None:
    """Stop and reap one isolated external-tool process group."""
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # The group leader should already have received SIGKILL.  This direct
        # fallback also handles unusual Popen/test doubles without leaking a
        # child while the private signing directory is removed.
        process.kill()
        process.wait(timeout=5)


def run_process(command: list[str], environment: dict[str, str], work: Path,
                label: str, *, return_stdout: bool = False,
                stdout_destination: Path | None = None,
                accepted_failure_stderr: bytes | None = None,
                timeout: int = PROCESS_TIMEOUT_SECONDS) -> str:
    stdout_path = stdout_destination or work / f"{label}.stdout"
    stderr_path = work / f"{label}.stderr"
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        stdout_path.chmod(0o600)
        stderr_path.chmod(0o600)
        process = None
        try:
            process = subprocess.Popen(
                command, cwd=work, env=environment, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, close_fds=True, start_new_session=True,
                preexec_fn=_child_limits,
            )
            try:
                return_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                kill_process_group_and_reap(process)
                fail(f"{label} timed out")
            except BaseException:
                kill_process_group_and_reap(process)
                raise
        except OSError:
            if process is not None:
                kill_process_group_and_reap(process)
            fail(f"{label} could not be executed")
    if (stdout_path.stat().st_size > MAX_PROCESS_LOG_BYTES
            or stderr_path.stat().st_size > MAX_PROCESS_LOG_BYTES):
        fail(f"{label} exceeded its private log limit")
    if return_code:
        if (accepted_failure_stderr is not None
                and not stdout_path.read_bytes()
                and stderr_path.read_bytes() == accepted_failure_stderr):
            return ""
        fail(f"{label} failed")
    if not return_stdout:
        return ""
    if stderr_path.stat().st_size:
        fail(f"{label} emitted unexpected diagnostics")
    try:
        return stdout_path.read_text(encoding="utf-8").strip()
    except UnicodeError:
        fail(f"{label} output is invalid")


def parse_signature_info(value: object, label: str, team: str, bundle_id: str,
                         *, require_entitlements: bool) -> None:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        fail(f"{label} must contain exactly one signed Mach-O entity")
    try:
        signature = value[0]["entity"]["mach_o"]["signature"]
        code_directory = signature["code_directory"]
        cms = signature["cms"]
    except (KeyError, TypeError):
        fail(f"{label} rcodesign metadata is incomplete")
    if (not isinstance(code_directory, dict)
            or code_directory.get("identifier") != bundle_id
            or code_directory.get("team_name") != team):
        fail(f"{label} code-directory identity differs from the selected profile")
    if not isinstance(cms, dict):
        fail(f"{label} has no cryptographic CMS signature")
    certificates = cms.get("certificates")
    signers = cms.get("signers")
    if (not isinstance(certificates, list) or not isinstance(signers, list)
            or len(signers) != 1 or not isinstance(signers[0], dict)
            or signers[0].get("signature_verifies") is not True):
        fail(f"{label} CMS signer could not be cryptographically verified")
    matching = [
        certificate for certificate in certificates
        if isinstance(certificate, dict)
        and certificate.get("apple_team_id") == team
    ]
    if len(matching) != 1:
        fail(f"{label} signer is not the selected Apple team")
    if not require_entitlements and (
            "entitlements_plist" in signature
            or "entitlements_der_plist" in signature):
        fail(f"{label} nested code unexpectedly contains entitlement metadata")
    xml_lines = signature.get("entitlements_plist")
    der_lines = signature.get("entitlements_der_plist")
    entitlements: dict = {}
    if isinstance(xml_lines, list) and all(isinstance(line, str) for line in xml_lines):
        try:
            parsed = plistlib.loads(("\n".join(xml_lines) + "\n").encode("utf-8"))
        except (ValueError, plistlib.InvalidFileException):
            fail(f"{label} XML entitlements are invalid")
        if not isinstance(parsed, dict):
            fail(f"{label} XML entitlements root is invalid")
        entitlements = parsed
    elif require_entitlements:
        fail(f"{label} XML entitlements are unavailable")
    if isinstance(der_lines, list) and all(isinstance(line, str) for line in der_lines):
        try:
            der = plistlib.loads(("\n".join(der_lines) + "\n").encode("utf-8"))
        except (ValueError, plistlib.InvalidFileException):
            fail(f"{label} DER entitlements are invalid")
        if der != entitlements:
            fail(f"{label} XML and DER entitlements disagree")
    if require_entitlements:
        if (entitlements.get("application-identifier") != f"{team}.{bundle_id}"
                or entitlements.get("com.apple.developer.team-identifier") != team):
            fail(f"{label} entitlements differ from the selected profile identity")


def macho_slices(executable: Path, label: str) -> list[bytes]:
    """Return bounded thin Mach-O slices from a thin or universal executable."""
    try:
        data = executable.read_bytes()
    except OSError:
        fail(f"{label} signed executable is unreadable")
    if not 0 < len(data) <= MAX_EXECUTABLE_BYTES:
        fail(f"{label} signed executable has an invalid size")
    if data[:4] not in {b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}:
        return [data]
    is_64 = data[:4] == b"\xca\xfe\xba\xbf"
    entry_size = 32 if is_64 else 20
    if len(data) < 8:
        fail(f"{label} universal Mach-O header is truncated")
    count = struct.unpack_from(">I", data, 4)[0]
    if not 0 < count <= 16 or 8 + count * entry_size > len(data):
        fail(f"{label} universal Mach-O slice table is invalid")
    slices: list[bytes] = []
    ranges: list[tuple[int, int]] = []
    for index in range(count):
        offset = 8 + index * entry_size
        if is_64:
            _cpu, _subtype, start, size, alignment, _reserved = struct.unpack_from(
                ">IIQQII", data, offset
            )
        else:
            _cpu, _subtype, start, size, alignment = struct.unpack_from(
                ">IIIII", data, offset
            )
        end = start + size
        if (not size or alignment > 31 or start % (1 << alignment)
                or start < 8 + count * entry_size or end > len(data)):
            fail(f"{label} universal Mach-O slice is invalid")
        if any(start < previous_end and previous_start < end
               for previous_start, previous_end in ranges):
            fail(f"{label} universal Mach-O slices overlap")
        ranges.append((start, end))
        slices.append(data[start:end])
    return slices


def code_signature_region(thin: bytes, label: str) -> bytes:
    formats = {
        b"\xce\xfa\xed\xfe": ("<", 28),
        b"\xcf\xfa\xed\xfe": ("<", 32),
        b"\xfe\xed\xfa\xce": (">", 28),
        b"\xfe\xed\xfa\xcf": (">", 32),
    }
    if thin[:4] not in formats:
        fail(f"{label} executable is not a supported thin Mach-O")
    endian, header_size = formats[thin[:4]]
    if len(thin) < header_size:
        fail(f"{label} Mach-O header is truncated")
    command_count, command_bytes = struct.unpack_from(endian + "II", thin, 16)
    command_end = header_size + command_bytes
    if command_count > 4096 or command_end > len(thin):
        fail(f"{label} Mach-O load-command table is invalid")
    offset = header_size
    regions: list[bytes] = []
    for _index in range(command_count):
        if offset + 8 > command_end:
            fail(f"{label} Mach-O load command is truncated")
        command, size = struct.unpack_from(endian + "II", thin, offset)
        if size < 8 or offset + size > command_end:
            fail(f"{label} Mach-O load-command size is invalid")
        if command == 0x1D:
            if size < 16:
                fail(f"{label} code-signature command is truncated")
            start, length = struct.unpack_from(endian + "II", thin, offset + 8)
            if not length or start + length > len(thin):
                fail(f"{label} code-signature range is invalid")
            regions.append(thin[start:start + length])
        offset += size
    if offset != command_end or len(regions) != 1:
        fail(f"{label} must contain exactly one Mach-O code-signature command")
    return regions[0]


def signature_blobs(region: bytes, label: str) -> dict[int, bytes]:
    if len(region) < 12:
        fail(f"{label} code-signature superblob is truncated")
    magic, total, count = struct.unpack_from(">III", region, 0)
    if (magic != 0xFADE0CC0 or not 12 <= total <= len(region)
            or count > 128 or 12 + count * 8 > total):
        fail(f"{label} code-signature superblob is invalid")
    blobs: dict[int, bytes] = {}
    occupied: list[tuple[int, int]] = []
    for index in range(count):
        slot, offset = struct.unpack_from(">II", region, 12 + index * 8)
        if slot in blobs or offset < 12 + count * 8 or offset + 8 > total:
            fail(f"{label} code-signature index is invalid")
        _blob_magic, length = struct.unpack_from(">II", region, offset)
        end = offset + length
        if length < 8 or end > total:
            fail(f"{label} code-signature blob range is invalid")
        if any(offset < previous_end and previous_start < end
               for previous_start, previous_end in occupied):
            fail(f"{label} code-signature blobs overlap")
        occupied.append((offset, end))
        blobs[slot] = region[offset:end]
    return blobs


def code_directory_string(blob: bytes, offset: int, label: str) -> str:
    if not 0 < offset < len(blob):
        fail(f"{label} code-directory string offset is invalid")
    end = blob.find(b"\0", offset)
    if end < 0:
        fail(f"{label} code-directory string is unterminated")
    try:
        return blob[offset:end].decode("ascii")
    except UnicodeDecodeError:
        fail(f"{label} code-directory string is not ASCII")


def validate_signature_slots(executable: Path, label: str, team: str,
                             bundle_id: str, *, require_entitlements: bool) -> None:
    for thin in macho_slices(executable, label):
        blobs = signature_blobs(code_signature_region(thin, label), label)
        directory_slots = [slot for slot in blobs if slot == 0 or 0x1000 <= slot <= 0x1005]
        if 0 not in directory_slots:
            fail(f"{label} lacks a primary code directory")
        for slot in directory_slots:
            blob = blobs[slot]
            if len(blob) < 52:
                fail(f"{label} code directory is truncated")
            magic, length, version = struct.unpack_from(">III", blob, 0)
            identifier_offset = struct.unpack_from(">I", blob, 20)[0]
            team_offset = struct.unpack_from(">I", blob, 48)[0]
            if (magic != 0xFADE0C02 or length != len(blob)
                    or version < 0x20200
                    or code_directory_string(blob, identifier_offset, label) != bundle_id
                    or code_directory_string(blob, team_offset, label) != team):
                fail(f"{label} code-directory identity differs from the profile")
        cms = blobs.get(0x10000)
        if cms is None or len(cms) <= 8 or struct.unpack_from(">I", cms, 0)[0] != 0xFADE0B01:
            fail(f"{label} lacks a cryptographic CMS signature slot")
        xml_blob = blobs.get(5)
        der_blob = blobs.get(7)
        if require_entitlements:
            if (xml_blob is None or len(xml_blob) <= 8
                    or struct.unpack_from(">I", xml_blob, 0)[0] != 0xFADE7171
                    or der_blob is None or len(der_blob) <= 8
                    or struct.unpack_from(">I", der_blob, 0)[0] != 0xFADE7172):
                fail(f"{label} lacks signed XML or DER entitlements")
            try:
                entitlements = plistlib.loads(xml_blob[8:])
            except (ValueError, plistlib.InvalidFileException):
                fail(f"{label} signed XML entitlements are invalid")
            if (not isinstance(entitlements, dict)
                    or entitlements.get("application-identifier") != f"{team}.{bundle_id}"
                    or entitlements.get("com.apple.developer.team-identifier") != team
                    or entitlements.get("get-task-allow") is not True):
                fail(f"{label} signed entitlements differ from the profile identity")
        elif xml_blob is not None or der_blob is not None:
            fail(f"{label} nested code unexpectedly contains application entitlements")


def verify_signer_leaf(rcodesign: Path, executable: Path, profile: dict,
                       expected_leaf: bytes, work: Path, label: str) -> None:
    openssl_name = shutil.which("openssl")
    if not openssl_name:
        fail("OpenSSL is required to verify the Mach-O signer")
    openssl = Path(openssl_name).resolve()
    cms_path = work / "signature.pem"
    code_directory = work / "code-directory.bin"
    signer_pem = work / "signer.pem"
    signer_der = work / "signer.der"
    run_process(
        [str(rcodesign), "extract", "--config-file", "/dev/null", "cms-pem",
         str(executable)],
        base_environment(work), work, f"{label}-extract-cms",
        stdout_destination=cms_path, timeout=60,
    )
    run_process(
        [str(rcodesign), "extract", "--config-file", "/dev/null",
         "code-directory-raw", str(executable)],
        base_environment(work), work, f"{label}-extract-code-directory",
        stdout_destination=code_directory, timeout=60,
    )
    run_process(
        [str(openssl), "cms", "-verify", "-inform", "PEM", "-noverify",
         "-in", str(cms_path), "-binary", "-content", str(code_directory),
         "-out", "/dev/null", "-signer", str(signer_pem)],
        base_environment(work), work, f"{label}-verify-cms", timeout=30,
    )
    run_process(
        [str(openssl), "x509", "-in", str(signer_pem), "-outform", "DER",
         "-out", str(signer_der)],
        base_environment(work), work, f"{label}-signer-der", timeout=15,
    )
    certificates = profile.get("DeveloperCertificates")
    if (not signer_der.is_file() or not isinstance(certificates, list)
            or signer_der.read_bytes() != expected_leaf
            or certificates.count(expected_leaf) != 1):
        fail(f"{label} signer leaf differs from the P12/profile identity")
    run_process(
        [str(openssl), "x509", "-in", str(signer_pem), "-noout", "-checkend",
         str(24 * 60 * 60)],
        base_environment(work), work, f"{label}-signer-validity", timeout=15,
    )


def extract_signed_executables(ipa: Path, work: Path) -> dict[str, Path]:
    root = f"Payload/{WDA_APP}"
    bundle_paths = {
        "runner": root,
        "xctest": f"{root}/{WDA_XCTEST}",
        "framework": f"{root}/{WDA_FRAMEWORK}",
    }
    result: dict[str, Path] = {}
    with zipfile.ZipFile(ipa) as archive:
        for label, bundle_path in bundle_paths.items():
            info = read_plist(archive, f"{bundle_path}/Info.plist", f"{label} Info.plist")
            executable = info["CFBundleExecutable"]
            data = read_member(
                archive, f"{bundle_path}/{executable}", MAX_EXECUTABLE_BYTES,
                f"{label} executable",
            )
            destination = work / f"{label}-executable"
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            result[label] = destination
    return result


def verify_macho_signatures(ipa: Path, rcodesign: Path, profile: dict,
                            expected_leaf: bytes, team: str, bundle_id: str,
                            work: Path) -> None:
    try:
        import yaml
    except ImportError:
        fail("python3-pyyaml is required for WDA signature verification")
    for label, executable in extract_signed_executables(ipa, work).items():
        expected_bundle_id = (
            bundle_id if label == "runner" else SOURCE_BUNDLE_IDS[label]
        )
        entity_work = work / f"verify-{label}"
        entity_work.mkdir(mode=0o700)
        run_process(
            [str(rcodesign), "verify", "--config-file", "/dev/null", str(executable)],
            base_environment(entity_work), entity_work, f"{label}-rcodesign", timeout=120,
        )
        metadata = run_process(
            [str(rcodesign), "print-signature-info", "--config-file", "/dev/null",
             str(executable)],
            base_environment(entity_work), entity_work, f"{label}-signature-info",
            return_stdout=True, accepted_failure_stderr=RCODESIGN_BER_DIAGNOSTIC,
            timeout=120,
        )
        if metadata:
            try:
                value = yaml.safe_load(metadata)
            except (yaml.YAMLError, ValueError):
                fail(f"{label} rcodesign metadata is unreadable")
            parse_signature_info(
                value, label, team, expected_bundle_id,
                require_entitlements=label == "runner",
            )
        else:
            validate_signature_slots(
                executable, label, team, expected_bundle_id,
                require_entitlements=label == "runner",
            )
        verify_signer_leaf(
            rcodesign, executable, profile, expected_leaf, entity_work, label
        )


def base_environment(work: Path) -> dict[str, str]:
    return {
        "HOME": str(work),
        "TMPDIR": str(work),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def write_task_openssl_config(work: Path) -> Path:
    """Enable Fedora's SHA-1 CMS switch for this private task only."""
    destination = work / "openssl-profile.cnf"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    content = (
        "openssl_conf = openssl_init\n"
        "\n"
        "[openssl_init]\n"
        "alg_section = evp_properties\n"
        "\n"
        "[evp_properties]\n"
        "rh-allow-sha1-signatures = yes\n"
    ).encode("ascii")
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    return destination


def openssl_environment(work: Path, config: Path) -> dict[str, str]:
    environment = base_environment(work)
    environment["OPENSSL_CONF"] = str(config)
    return environment


def validate_resigner_version(resigner: Path, work: Path) -> None:
    value = run_process(
        [str(resigner), "--version"], base_environment(work), work,
        "resigner-version", return_stdout=True, timeout=30,
    )
    if value != RESIGNER_VERSION_OUTPUT:
        fail("resigner version differs from the required v0.3.1 pin")


def validate_rcodesign_version(rcodesign: Path, work: Path) -> None:
    value = run_process(
        [str(rcodesign), "--version"], base_environment(work), work,
        "rcodesign-version", return_stdout=True, timeout=30,
    )
    if value != "apple-codesign 0.29.0":
        fail("rcodesign version differs from the required 0.29.0 pin")


def verify_profile_payload(profile: Path, apple_root: Path, openssl_config: Path,
                           work: Path) -> dict:
    """Verify the profile CMS chain with one pinned root and task-local policy."""
    openssl_name = shutil.which("openssl")
    if not openssl_name:
        fail("OpenSSL is required to verify the WDA profile")
    openssl = Path(openssl_name).resolve()
    if not openssl.is_file() or not os.access(openssl, os.X_OK):
        fail("OpenSSL executable is invalid")
    root_der = work / "apple-root-ca.der"
    run_process(
        [str(openssl), "x509", "-in", str(apple_root), "-outform", "DER"],
        openssl_environment(work, openssl_config), work, "root-ca-der",
        stdout_destination=root_der, timeout=15,
    )
    if (not root_der.is_file()
            or sha256_file(root_der) != APPLE_ROOT_CA_DER_SHA256):
        fail("Apple Root CA DER failed its exact public trust-anchor pin")
    decoded = work / "verified-profile.plist"
    run_process(
        [str(openssl), "cms", "-verify", "-inform", "DER", "-binary",
         "-purpose", "any", "-CAfile", str(apple_root), "-in", str(profile),
         "-out", str(decoded)],
        openssl_environment(work, openssl_config), work, "profile-cms", timeout=30,
    )
    if (not decoded.is_file() or decoded.is_symlink()
            or not 0 < decoded.stat().st_size <= MAX_PROFILE_BYTES):
        fail("WDA profile payload is invalid")
    try:
        value = plistlib.loads(decoded.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        fail("WDA profile payload is not a plist")
    if not isinstance(value, dict):
        fail("WDA profile payload root is invalid")
    return value


def profile_identity(value: dict, device_udid: str) -> tuple[str, str]:
    teams = value.get("TeamIdentifier")
    prefixes = value.get("ApplicationIdentifierPrefix")
    entitlements = value.get("Entitlements")
    creation = value.get("CreationDate")
    expiry = value.get("ExpirationDate")
    devices = value.get("ProvisionedDevices")
    platforms = value.get("Platform")
    certificates = value.get("DeveloperCertificates")
    if (not isinstance(teams, list) or len(teams) != 1
            or not isinstance(teams[0], str) or not TEAM_RE.fullmatch(teams[0])
            or prefixes != teams or not isinstance(entitlements, dict)
            or not isinstance(creation, datetime) or not isinstance(expiry, datetime)
            or value.get("LocalProvision") is not True
            or value.get("IsXcodeManaged") is not True
            or value.get("TimeToLive") != 7
            or value.get("ProvisionsAllDevices") not in (None, False)
            or not isinstance(devices, list) or not devices or device_udid not in devices
            or any(not isinstance(device, str) or not device for device in devices)
            or len(set(devices)) != len(devices)
            or not isinstance(platforms, list) or "iOS" not in platforms
            or any(not isinstance(platform, str) or not platform for platform in platforms)
            or len(set(platforms)) != len(platforms)
            or not isinstance(certificates, list) or not certificates
            or any(not isinstance(certificate, bytes) or not certificate
                   for certificate in certificates)
            or len(set(certificates)) != len(certificates)):
        fail("WDA profile lacks a complete Personal-Team development identity")
    team = teams[0]
    application_id = entitlements.get("application-identifier")
    prefix = f"{team}."
    if (not isinstance(application_id, str) or not application_id.startswith(prefix)
            or application_id.count("*") or not BUNDLE_RE.fullmatch(
                application_id[len(prefix):]
            ) or entitlements.get("com.apple.developer.team-identifier") != team
            or entitlements.get("get-task-allow") is not True):
        fail("WDA profile must authorize one explicit development bundle ID")
    creation = creation.replace(
        tzinfo=creation.tzinfo or timezone.utc
    ).astimezone(timezone.utc)
    expiry = expiry.replace(tzinfo=expiry.tzinfo or timezone.utc).astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if (creation > now + PROFILE_CLOCK_TOLERANCE or expiry <= creation
            or expiry - creation > (
                PERSONAL_TEAM_PROFILE_LIFETIME + PROFILE_CLOCK_TOLERANCE
            )
            or expiry > now + (
                PERSONAL_TEAM_PROFILE_LIFETIME + PROFILE_CLOCK_TOLERANCE
            )):
        fail("WDA profile is not a current seven-day Personal-Team profile")
    if expiry < now + timedelta(hours=24):
        fail("WDA profile has less than 24 hours remaining")
    return team, application_id[len(prefix):]


def count_pem_blocks(value: bytes, label: bytes) -> int:
    return value.count(b"-----BEGIN " + label + b"-----")


def verify_p12_identity(p12: Path, password: str, profile: dict, team: str,
                        openssl_config: Path, work: Path) -> bytes:
    openssl_name = shutil.which("openssl")
    if not openssl_name:
        fail("OpenSSL is required to verify the Personal-Team P12")
    openssl = Path(openssl_name).resolve()
    environment = openssl_environment(work, openssl_config)
    environment["P12_PASSWORD"] = password
    certificates_pem = work / "p12-leaf.pem"
    private_keys_pem = work / "p12-private-key.pem"
    run_process(
        [str(openssl), "pkcs12", "-legacy", "-in", str(p12), "-passin",
         "env:P12_PASSWORD", "-clcerts", "-nokeys"],
        environment, work, "p12-certificates", stdout_destination=certificates_pem,
        timeout=30,
    )
    run_process(
        [str(openssl), "pkcs12", "-legacy", "-in", str(p12), "-passin",
         "env:P12_PASSWORD", "-nocerts", "-nodes"],
        environment, work, "p12-private-keys", stdout_destination=private_keys_pem,
        timeout=30,
    )
    environment.pop("P12_PASSWORD", None)
    certificate_bytes = certificates_pem.read_bytes()
    key_bytes = private_keys_pem.read_bytes()
    key_count = sum(count_pem_blocks(key_bytes, label) for label in (
        b"PRIVATE KEY", b"RSA PRIVATE KEY", b"EC PRIVATE KEY"
    ))
    if count_pem_blocks(certificate_bytes, b"CERTIFICATE") != 1 or key_count != 1:
        fail("Personal-Team P12 must contain exactly one leaf and private key")
    leaf_der = work / "p12-leaf.der"
    certificate_public = work / "p12-certificate-public.pem"
    key_public = work / "p12-key-public.pem"
    run_process(
        [str(openssl), "x509", "-in", str(certificates_pem), "-outform", "DER"],
        openssl_environment(work, openssl_config), work, "p12-leaf-der",
        stdout_destination=leaf_der, timeout=15,
    )
    run_process(
        [str(openssl), "x509", "-in", str(certificates_pem), "-pubkey", "-noout"],
        openssl_environment(work, openssl_config), work, "p12-certificate-public",
        stdout_destination=certificate_public, timeout=15,
    )
    run_process(
        [str(openssl), "pkey", "-in", str(private_keys_pem), "-pubout"],
        openssl_environment(work, openssl_config), work, "p12-key-public",
        stdout_destination=key_public, timeout=15,
    )
    try:
        private_keys_pem.unlink()
    except OSError:
        fail("temporary P12 private-key material could not be removed")
    key_bytes = b""
    leaf = leaf_der.read_bytes()
    developer_certificates = profile.get("DeveloperCertificates")
    if (not 0 < len(leaf) <= MAX_CERTIFICATE_BYTES
            or certificate_public.read_bytes() != key_public.read_bytes()
            or not isinstance(developer_certificates, list)
            or developer_certificates.count(leaf) != 1):
        fail("P12 key/leaf/profile identity does not match exactly")
    subject = run_process(
        [str(openssl), "x509", "-in", str(certificates_pem), "-subject", "-noout",
         "-nameopt", "RFC2253"],
        openssl_environment(work, openssl_config), work, "p12-leaf-subject",
        return_stdout=True, timeout=15,
    )
    if re.search(rf"(?:^|,)OU={re.escape(team)}(?:,|$)",
                 subject.removeprefix("subject=")) is None:
        fail("P12 leaf subject does not name the selected Personal Team")
    run_process(
        [str(openssl), "x509", "-in", str(certificates_pem), "-noout",
         "-checkend", str(24 * 60 * 60)],
        openssl_environment(work, openssl_config), work, "p12-leaf-validity",
        timeout=15,
    )
    return leaf


def copy_private(source: Path, destination: Path, maximum: int) -> None:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    copied = 0
    try:
        with source.open("rb") as input_stream, os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            while block := input_stream.read(1024 * 1024):
                copied += len(block)
                if copied > maximum:
                    fail("private signing input exceeded its copy limit")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if copied != source.stat().st_size:
        fail("private signing input changed while it was copied")


def signing_command(arguments: argparse.Namespace, profile_dir: Path, target: Path,
                    team: str, bundle_id: str) -> list[str]:
    command = [
        str(arguments.resigner),
        "--p12-file", str(arguments.p12_file),
        "--profile", str(profile_dir),
        "--force",
        "--team-id", team,
    ]
    command.extend((
        "--bundle-id-remap",
        f"{SOURCE_BUNDLE_IDS['runner']}={bundle_id}",
    ))
    command.append(str(target))
    return command


def extract_private_ipa(ipa: Path, destination: Path) -> Path:
    """Extract one already-inspected IPA without preserving unsafe host metadata."""
    destination.mkdir(mode=0o700)
    try:
        archive = zipfile.ZipFile(ipa)
    except (OSError, zipfile.BadZipFile):
        fail("signed WDA IPA could not be opened for recursive verification")
    with archive:
        entries, _names = inspect_archive(archive)
        for entry in entries:
            relative = safe_member_name(entry.filename)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if entry.is_dir():
                target.mkdir(mode=0o700, exist_ok=True)
                continue
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o700 if entry.external_attr >> 16 & 0o111 else 0o600,
            )
            written = 0
            try:
                with archive.open(entry) as source, os.fdopen(descriptor, "wb") as output:
                    descriptor = -1
                    while block := source.read(1024 * 1024):
                        written += len(block)
                        if written > entry.file_size:
                            fail("signed WDA IPA member expanded beyond its metadata")
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            if written != entry.file_size:
                fail("signed WDA IPA member is truncated")
    application = destination / "Payload" / WDA_APP
    if not application.is_dir() or application.is_symlink():
        fail("signed WDA extraction lacks its fixed application")
    return application


def repackage_private_tree(source_root: Path, destination: Path, label: str) -> None:
    try:
        with zipfile.ZipFile(
                destination, "x", compression=zipfile.ZIP_DEFLATED,
                compresslevel=6, allowZip64=True) as archive:
            for source in sorted(source_root.rglob("*")):
                if source.is_symlink():
                    fail(f"{label} contains a symbolic link")
                relative = source.relative_to(source_root).as_posix()
                if source.is_dir():
                    information = zipfile.ZipInfo(relative + "/")
                    information.external_attr = (stat.S_IFDIR | 0o700) << 16
                    archive.writestr(information, b"")
                elif source.is_file():
                    if source.stat().st_size > MAX_MEMBER_BYTES:
                        fail(f"{label} contains an oversized file")
                    information = zipfile.ZipInfo(relative)
                    mode = 0o700 if source.stat().st_mode & 0o111 else 0o600
                    information.external_attr = (stat.S_IFREG | mode) << 16
                    information.compress_type = zipfile.ZIP_DEFLATED
                    with source.open("rb") as input_stream, archive.open(
                            information, "w", force_zip64=True) as output:
                        shutil.copyfileobj(input_stream, output, 1024 * 1024)
                else:
                    fail(f"{label} contains a non-regular entry")
    except (OSError, ValueError, zipfile.BadZipFile):
        fail(f"{label} could not be repackaged")
    destination.chmod(0o600)
    if not 0 < destination.stat().st_size <= MAX_IPA_BYTES:
        fail(f"{label} IPA size is invalid")


def prepare_outer_runner_for_resigner(target: Path, work: Path) -> Path:
    """Keep the fixed XCTest payload away from the profile-oriented resigner."""
    extraction = work / "outer-resigner-input"
    application = extract_private_ipa(target, extraction)
    nested = application / WDA_XCTEST
    if not nested.is_dir() or nested.is_symlink():
        fail("unsigned WDA extraction lacks its fixed XCTest bundle")
    saved_nested = work / "unsigned-xctest"
    try:
        nested.rename(saved_nested)
    except OSError:
        fail("unsigned WDA XCTest bundle could not be isolated")
    debug_symbols = application / "PlugIns" / "WebDriverAgentRunner.xctest.dSYM"
    if debug_symbols.exists():
        if not debug_symbols.is_dir() or debug_symbols.is_symlink():
            fail("WDA debug-symbol bundle is unsafe")
        shutil.rmtree(debug_symbols)
    outer_only = work / "outer-resigner-input.ipa"
    repackage_private_tree(extraction, outer_only, "outer-only WDA")
    try:
        os.replace(outer_only, target)
    except OSError:
        fail("outer-only WDA could not replace its private intermediate")
    return saved_nested


def write_signing_entitlements(profile: dict, work: Path) -> Path:
    entitlements = profile.get("Entitlements")
    if not isinstance(entitlements, dict):
        fail("WDA profile entitlements are unavailable for recursive signing")
    destination = work / "signing-entitlements.plist"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            plistlib.dump(entitlements, output, fmt=plistlib.FMT_XML, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
    except (OSError, TypeError, ValueError):
        fail("WDA profile entitlements could not be serialized")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return destination


def rcodesign_command(arguments: argparse.Namespace, application: Path,
                      entitlements: Path, team: str) -> list[str]:
    return [
        str(arguments.rcodesign), "sign", "--config-file", "/dev/null",
        "--p12-file", str(arguments.p12_file),
        "--p12-password-file", str(arguments.p12_password_file),
        "--team-name", team,
        "--timestamp-url", "none",
        "--entitlements-xml-file", str(entitlements),
        str(application),
    ]


def recursively_rcodesign_wda(arguments: argparse.Namespace, target: Path,
                              profile: dict, team: str, work: Path,
                              unsigned_xctest: Path) -> None:
    extraction = work / "recursive-signing"
    application = extract_private_ipa(target, extraction)
    debug_symbols = application / "PlugIns" / "WebDriverAgentRunner.xctest.dSYM"
    if debug_symbols.exists():
        if not debug_symbols.is_dir() or debug_symbols.is_symlink():
            fail("WDA debug-symbol bundle is unsafe")
        shutil.rmtree(debug_symbols)
    # The xctrunner application is the provisioned main executable.  Its
    # loadable XCTest plug-in is signed by the same certificate, but it must
    # not carry application entitlements or an embedded profile.  iOS AMFI
    # rejects such entitlements on a non-main Mach-O before WDA can open 8100.
    nested = application / WDA_XCTEST
    if nested.exists():
        fail("outer resigner unexpectedly injected a nested XCTest bundle")
    try:
        shutil.copytree(unsigned_xctest, nested, copy_function=shutil.copy2)
    except OSError:
        fail("fixed unsigned XCTest bundle could not be restored")
    for profile_name in ("embedded.mobileprovision", "embedded.provisionprofile"):
        if (nested / profile_name).exists():
            fail("fixed unsigned XCTest bundle unexpectedly contains a profile")
    entitlements = write_signing_entitlements(profile, work)
    run_process(
        rcodesign_command(arguments, application, entitlements, team),
        base_environment(work), work, "rcodesign-recursive-sign", timeout=300,
    )
    repacked = work / "rcodesign-wda.ipa"
    repackage_private_tree(extraction, repacked, "recursively signed WDA")
    try:
        os.replace(repacked, target)
    except OSError:
        fail("recursively signed WDA could not replace its private intermediate")


def inspect_outer_resigner_output(path: Path, target_bundle_id: str,
                                  profile_bytes: bytes) -> None:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        fail("outer resigner output is not a valid IPA")
    with archive:
        _entries, names = inspect_archive(archive)
        root = f"Payload/{WDA_APP}"
        if any(name not in {"Payload", root} and not name.startswith(root + "/")
               for name in names):
            fail("outer resigner output contains content outside its fixed application")
        nested_prefix = f"{root}/{WDA_XCTEST}"
        if any(name == nested_prefix or name.startswith(nested_prefix + "/")
               for name in names):
            fail("outer resigner unexpectedly injected a nested XCTest bundle")
        runner = read_plist(archive, f"{root}/Info.plist", "signed runner Info.plist")
        validate_bundle_plist(
            runner, target_bundle_id, "APPL", "signed runner",
            EXPECTED_EXECUTABLES["runner"],
        )
        required = {
            f"{root}/_CodeSignature/CodeResources",
            f"{root}/embedded.mobileprovision",
        }
        if not required.issubset(names):
            fail("outer resigner output lacks its profile or CodeResources")
        embedded_profiles = {
            name for name in names
            if PurePosixPath(name).name in {
                "embedded.mobileprovision", "embedded.provisionprofile"
            }
        }
        if embedded_profiles != {f"{root}/embedded.mobileprovision"}:
            fail("only the outer WDA runner may embed a provisioning profile")
        if read_member(
                archive, f"{root}/embedded.mobileprovision", MAX_PROFILE_BYTES,
                "embedded profile") != profile_bytes:
            fail("outer resigner output does not embed the selected profile")


def inspect_signed_wda(path: Path, target_bundle_id: str, profile_bytes: bytes) -> None:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        fail("resigner output is not a valid IPA")
    with archive:
        _entries, names = inspect_archive(archive)
        root = f"Payload/{WDA_APP}"
        if any(name not in {"Payload", root} and not name.startswith(root + "/")
               for name in names):
            fail("signed WDA IPA contains content outside its fixed application")
        runner = read_plist(archive, f"{root}/Info.plist", "signed runner Info.plist")
        xctest = read_plist(
            archive, f"{root}/{WDA_XCTEST}/Info.plist", "signed XCTest Info.plist"
        )
        framework = read_plist(
            archive, f"{root}/{WDA_FRAMEWORK}/Info.plist", "signed framework Info.plist"
        )
        validate_bundle_plist(
            runner, target_bundle_id, "APPL", "signed runner",
            EXPECTED_EXECUTABLES["runner"],
        )
        validate_bundle_plist(
            xctest, SOURCE_BUNDLE_IDS["xctest"], "BNDL", "signed XCTest",
            EXPECTED_EXECUTABLES["xctest"],
        )
        validate_bundle_plist(
            framework, SOURCE_BUNDLE_IDS["framework"], "FMWK", "signed framework",
            EXPECTED_EXECUTABLES["framework"],
        )
        required = {
            f"{root}/_CodeSignature/CodeResources",
            f"{root}/embedded.mobileprovision",
            f"{root}/{WDA_XCTEST}/_CodeSignature/CodeResources",
            f"{root}/{WDA_FRAMEWORK}/_CodeSignature/CodeResources",
        }
        if not required.issubset(names):
            fail("signed WDA lacks recursive profile or CodeResources output")
        forbidden_framework_profiles = {
            f"{root}/{WDA_FRAMEWORK}/embedded.mobileprovision",
            f"{root}/{WDA_FRAMEWORK}/embedded.provisionprofile",
        }
        if names & forbidden_framework_profiles:
            fail("signed WDA framework must never embed a provisioning profile")
        nested_profiles = {
            f"{root}/{WDA_XCTEST}/embedded.mobileprovision",
            f"{root}/{WDA_XCTEST}/embedded.provisionprofile",
        }
        if names & nested_profiles:
            fail("signed WDA XCTest plug-in must not embed a provisioning profile")
        embedded_profiles = {
            name for name in names
            if PurePosixPath(name).name in {
                "embedded.mobileprovision", "embedded.provisionprofile"
            }
        }
        if embedded_profiles != {f"{root}/embedded.mobileprovision"}:
            fail("only the outer WDA runner may embed a provisioning profile")
        profile_members = [f"{root}/embedded.mobileprovision"]
        for member in profile_members:
            if read_member(archive, member, MAX_PROFILE_BYTES, "embedded profile") \
                    != profile_bytes:
                fail("signed WDA does not embed the explicitly selected profile")


def publish_no_replace(target: Path, output: Path) -> None:
    """Atomically publish a complete file without replacing a raced output."""
    try:
        os.link(target, output, follow_symlinks=False)
    except FileExistsError:
        fail("signed WDA output appeared during signing")
    except OSError:
        fail("signed WDA output could not be atomically published")
    try:
        target.unlink()
        directory_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError:
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        fail("signed WDA output publication could not be made durable")


@contextmanager
def interruption_cleanup():
    previous: dict[int, object] = {}

    def interrupted(_signal_number, _frame):
        raise SigningError("offline WDA signing was interrupted")

    for signal_number in (signal.SIGINT, signal.SIGTERM):
        previous[signal_number] = signal.getsignal(signal_number)
        signal.signal(signal_number, interrupted)
    try:
        yield
    finally:
        for signal_number, handler in previous.items():
            signal.signal(signal_number, handler)


def run(arguments: argparse.Namespace) -> int:
    if sys.platform != "linux":
        fail("offline Personal-Team WDA signing is supported only on Linux")
    validate_paths(arguments)
    validate_kit_manifest(arguments.unsigned_kit_manifest, arguments.unsigned_wda_ipa)
    inspect_unsigned_wda(arguments.unsigned_wda_ipa)
    device_udid = read_device_udid(arguments.device_udid_file)
    temporary = Path(tempfile.mkdtemp(prefix=".wda-sign-", dir=arguments.output_ipa.parent))
    temporary.chmod(0o700)
    password = ""
    try:
        validate_resigner_version(arguments.resigner, temporary)
        validate_rcodesign_version(arguments.rcodesign, temporary)
        openssl_config = write_task_openssl_config(temporary)
        profile_value = verify_profile_payload(
            arguments.profile_file, arguments.apple_root_ca_pem, openssl_config,
            temporary,
        )
        team, target_bundle_id = profile_identity(profile_value, device_udid)
        device_udid = ""
        password = read_password(arguments.p12_password_file)
        expected_leaf = verify_p12_identity(
            arguments.p12_file, password, profile_value, team, openssl_config,
            temporary,
        )
        isolated_profiles = temporary / "profiles"
        isolated_profiles.mkdir(mode=0o700)
        isolated_profile = isolated_profiles / "wda.mobileprovision"
        copy_private(arguments.profile_file, isolated_profile, MAX_PROFILE_BYTES)
        profile_bytes = isolated_profile.read_bytes()
        target = temporary / "signed-wda.ipa"
        copy_private(arguments.unsigned_wda_ipa, target, MAX_IPA_BYTES)
        unsigned_xctest = prepare_outer_runner_for_resigner(target, temporary)
        environment = base_environment(temporary)
        environment["P12_PASSWORD"] = password
        run_process(
            signing_command(
                arguments, isolated_profiles, target, team, target_bundle_id
            ),
            environment, temporary, "resigner-sign",
        )
        environment.pop("P12_PASSWORD", None)
        password = ""
        run_process(
            [str(arguments.resigner), "--profile", str(isolated_profiles),
             "--team-id", team, "--only-verify", str(target)],
            base_environment(temporary), temporary, "resigner-verify",
        )
        if (not target.is_file() or target.is_symlink()
                or not 0 < target.stat().st_size <= MAX_IPA_BYTES):
            fail("resigner output file is invalid")
        inspect_outer_resigner_output(target, target_bundle_id, profile_bytes)
        recursively_rcodesign_wda(
            arguments, target, profile_value, team, temporary, unsigned_xctest
        )
        inspect_signed_wda(target, target_bundle_id, profile_bytes)
        run_process(
            [str(arguments.resigner), "--profile", str(isolated_profiles),
             "--team-id", team, "--only-verify", str(target)],
            base_environment(temporary), temporary, "resigner-final-verify",
        )
        verify_macho_signatures(
            target, arguments.rcodesign, profile_value, expected_leaf, team,
            target_bundle_id, temporary,
        )
        target.chmod(0o600)
        with target.open("rb") as signed:
            os.fsync(signed.fileno())
        if arguments.output_ipa.exists():
            fail("signed WDA output appeared during signing")
        publish_no_replace(target, arguments.output_ipa)
    finally:
        password = ""
        device_udid = ""
        shutil.rmtree(temporary, ignore_errors=True)
    print(
        "PASS: WDA recursively signed and cryptographically verified offline; "
        "device ProfileValidated/installation remains the Apple policy gate"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unsigned-wda-ipa", type=Path, required=True)
    parser.add_argument("--unsigned-kit-manifest", type=Path, required=True)
    parser.add_argument("--p12-file", type=Path, required=True)
    parser.add_argument("--p12-password-file", type=Path, required=True)
    parser.add_argument("--profile-file", type=Path, required=True)
    parser.add_argument("--device-udid-file", type=Path, required=True)
    parser.add_argument("--apple-root-ca-pem", type=Path, required=True)
    parser.add_argument("--resigner", type=Path, required=True)
    parser.add_argument("--rcodesign", type=Path, required=True)
    parser.add_argument("--output-ipa", type=Path, required=True)
    try:
        arguments = parser.parse_args()
        with interruption_cleanup():
            return run(arguments)
    except SigningError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, zipfile.BadZipFile):
        print("error: offline WDA signing failed safely", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
