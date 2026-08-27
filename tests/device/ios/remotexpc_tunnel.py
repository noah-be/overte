#!/usr/bin/env python3
"""Manage the pinned, privacy-redacted RemoteXPC tunnel used by Fedora Appium."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from urllib.error import URLError
from urllib.request import urlopen


LOCK_FILE = Path(__file__).with_name("toolchain.lock.json")
PACKAGE_FILE = Path(__file__).with_name("package.json")
NPM_LOCK_FILE = Path(__file__).with_name("package-lock.json")
DEVICE_PREFLIGHT_FILE = Path(__file__).with_name("appium_device_preflight.js")
DEVICE_INSTALL_FILE = Path(__file__).with_name("appium_device_install.js")
DEVICE_DDI_FILE = Path(__file__).with_name("appium_device_ddi.js")
ARTIFACT_TREE_FILE = Path(__file__).with_name("private_artifact_tree.py")
DEFAULT_PORT = 42314
TUNNEL_PORT_ITEM = Path(
    "appium-xcuitest-driver-nodejs/strongbox/tunnelRegistryPort"
)
UNIT_NAME = "overte-ios-remotexpc.service"
SERVICE_ROOT = Path("/usr/local/lib/overte-ios-remotexpc")
SERVICE_STATE_DIRECTORY = "overte-ios-remotexpc"
SERVICE_STATE_ROOT = Path("/var/lib") / SERVICE_STATE_DIRECTORY
SYSTEM_RUNTIME_PARENT_CHAIN = (
    Path("/"), Path("/usr"), Path("/usr/local"), Path("/usr/local/lib"), SERVICE_ROOT,
)
UNIT_PATH = Path("/etc/systemd/system") / UNIT_NAME
RUNTIME_MARKER = "service-runtime.json"
RESTORECON_CANDIDATES = (Path("/usr/bin/restorecon"), Path("/usr/sbin/restorecon"))
SELINUX_ENFORCE_FILE = Path("/sys/fs/selinux/enforce")
OVERFLOW_UID_FILE = Path("/proc/sys/kernel/overflowuid")
APPIUM_EXTENSION_TEMPLATE = "appium-extensions.yaml"
MAX_APPIUM_EXTENSION_BYTES = 128 * 1024
DEVICE_TOKEN_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])[0-9a-fA-F]{24,64}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}(?![A-Za-z0-9])"),
)
PROTECTED_RECEIPT = "overte-ios-fedora-e2e-receipt-v1"
PERSONAL_RECEIPT = "overte-ios-personal-team-artifact-receipt-v1"
OVERTE_BUNDLE_ID = "org.overte.interface.e2e"
WDA_BUNDLE_ID = "org.overte.WebDriverAgentRunner.xctrunner"
BUNDLE_ID_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+"
)
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_IPA_BYTES = 4 * 1024 * 1024 * 1024


IOS_ROOT = Path(__file__).resolve().parent
if str(IOS_ROOT) not in sys.path:
    sys.path.insert(0, str(IOS_ROOT))
from private_artifact_tree import (  # noqa: E402
    ArtifactTreeError,
    tree_sha256 as artifact_tree_sha256,
)


class TunnelError(RuntimeError):
    """RemoteXPC service configuration is unsafe or unavailable."""


def fail(message: str) -> "NoReturn":
    raise TunnelError(message)


def redact(line: str, explicit: set[str]) -> str:
    result = line
    for token in sorted(explicit, key=len, reverse=True):
        if token:
            result = result.replace(token, "<redacted-device>")
    for pattern in DEVICE_TOKEN_PATTERNS:
        result = pattern.sub("<redacted-device>", result)
    return result


def private_device_tokens() -> set[str]:
    executable = shutil.which("idevice_id")
    if not executable:
        return set()
    result = subprocess.run(
        [executable, "-l"], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=10, check=False,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def load_lock(path: Path = LOCK_FILE) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1:
        fail("unsupported toolchain lock")
    return value


def remote_xpc_lock(lock: dict) -> dict:
    try:
        runtime = lock["appium"]["iosRuntime"]["remoteXpc"]
    except (KeyError, TypeError):
        fail("toolchain lock has no RemoteXPC runtime")
    if (not isinstance(runtime, dict) or not isinstance(runtime.get("package"), str)
            or not re.fullmatch(r"(?:@[a-z0-9._-]+/)?[a-z0-9._-]+", runtime["package"])
            or not isinstance(runtime.get("version"), str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?",
                                runtime["version"])):
        fail("toolchain lock has an invalid RemoteXPC runtime")
    return runtime


def resolve_package(node_modules: Path, lock: dict) -> Path:
    runtime = remote_xpc_lock(lock)
    candidates = (
        node_modules / runtime["package"],
        node_modules / "appium-xcuitest-driver" / "node_modules" / runtime["package"],
    )
    package_root = next((path for path in candidates if (path / "package.json").is_file()), None)
    if package_root is None:
        fail("pinned appium-ios-remotexpc package is not installed")
    metadata = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    if metadata.get("name") != runtime["package"] or metadata.get("version") != runtime["version"]:
        fail("installed appium-ios-remotexpc does not match the toolchain lock")
    tunnel_script = package_root / "scripts" / "tunnel-creation.mjs"
    if not tunnel_script.is_file():
        fail("installed appium-ios-remotexpc has no tunnel entry point")
    return package_root


def validate_appium_project(appium_home: Path, lock: dict) -> tuple[Path, Path]:
    if (not appium_home.is_absolute() or appium_home.is_symlink()
            or not appium_home.is_dir()):
        fail("Appium runtime project must be a safe absolute directory")
    for source, expected, label in (
        (appium_home / "package.json", PACKAGE_FILE, "package.json"),
        (appium_home / "package-lock.json", NPM_LOCK_FILE, "package-lock.json"),
    ):
        if (source.is_symlink() or not source.is_file()
                or file_sha256(source) != file_sha256(expected)):
            fail(f"Appium runtime {label} differs from the checked-in exact lock")
    direct = {
        "appium": lock["appium"]["core"]["version"],
        "appium-xcuitest-driver": lock["appium"]["drivers"]["xcuitest"]["version"],
        lock["appium"]["iosRuntime"]["remoteXpc"]["package"]:
            lock["appium"]["iosRuntime"]["remoteXpc"]["version"],
        lock["appium"]["iosRuntime"]["webdriverAgent"]["package"]:
            lock["appium"]["iosRuntime"]["webdriverAgent"]["version"],
    }
    node_modules = appium_home / "node_modules"
    if node_modules.is_symlink() or not node_modules.is_dir():
        fail("Appium runtime has no ordinary node_modules tree")
    for package_name, version in direct.items():
        metadata_path = node_modules / package_name / "package.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail(f"Appium runtime lacks pinned package {package_name}")
        if metadata.get("name") != package_name or metadata.get("version") != version:
            fail(f"Appium runtime package {package_name} differs from its exact pin")
    appium_entry = node_modules / "appium" / "build" / "lib" / "main.js"
    ios_device = (
        node_modules / "appium-xcuitest-driver/node_modules/appium-ios-device/package.json"
    )
    real_device = (
        node_modules
        / "appium-xcuitest-driver/build/lib/device/real-device-management.js"
    )
    package_root = resolve_package(node_modules, lock)
    tunnel_script = package_root / "scripts" / "tunnel-creation.mjs"
    if not appium_entry.is_file() or appium_entry.is_symlink():
        fail("Appium server entry point is unavailable")
    try:
        ios_device_metadata = json.loads(ios_device.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("Appium runtime lacks its pinned installation-proxy helper")
    if (ios_device.is_symlink() or ios_device_metadata.get("name") != "appium-ios-device"
            or ios_device_metadata.get("version") != "3.1.21"):
        fail("Appium installation-proxy helper differs from its package-lock pin")
    if real_device.is_symlink() or not real_device.is_file():
        fail("Appium immutable device-install helper entry point is unavailable")
    return appium_entry, tunnel_script


def list_installed_drivers(node: Path, appium_entry: Path, appium_home: Path,
                           working_directory: Path) -> dict:
    """Ask the pinned Appium itself to discover and validate its extensions."""
    environment = os.environ.copy()
    environment["APPIUM_HOME"] = str(appium_home)
    environment["PATH"] = str(node.parent) + ":/usr/sbin:/usr/bin"
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(
            [str(node), str(appium_entry), "driver", "list", "--installed", "--json"],
            cwd=working_directory, env=environment, stdout=output,
            stderr=subprocess.DEVNULL, timeout=120, check=False,
        )
        size = output.tell()
        if result.returncode or not 0 < size <= MAX_APPIUM_EXTENSION_BYTES:
            fail("Appium could not attest its installed driver registry")
        output.seek(0)
        try:
            value = json.loads(output.read(MAX_APPIUM_EXTENSION_BYTES + 1))
        except (UnicodeError, json.JSONDecodeError):
            fail("Appium returned invalid installed-driver metadata")
    expected = load_lock()["appium"]["drivers"]["xcuitest"]
    if (not isinstance(value, dict) or set(value) != {"xcuitest"}
            or not isinstance(value["xcuitest"], dict)
            or value["xcuitest"].get("version") != expected["version"]
            or value["xcuitest"].get("pkgName") != expected["package"]
            or value["xcuitest"].get("automationName") != "XCUITest"):
        fail("Appium did not discover exactly the pinned XCUITest driver")
    return value


def service_runtime_revision(lock: dict) -> int:
    revision = lock.get("serviceRuntimeRevision")
    if revision != 7:
        fail("unsupported immutable service-runtime revision")
    return revision


def prepare_appium_extension_template(appium_home: Path, node: Path,
                                      destination: Path, template: Path) -> None:
    """Generate Appium's registry while staging is writable, then relocate it."""
    appium_entry = appium_home / "node_modules/appium/build/lib/main.js"
    list_installed_drivers(node, appium_entry, appium_home, appium_home)
    manifest = appium_home / "node_modules/.cache/appium/extensions.yaml"
    try:
        contents = manifest.read_bytes()
    except OSError:
        fail("Appium did not materialize its extension registry")
    if not 0 < len(contents) <= MAX_APPIUM_EXTENSION_BYTES:
        fail("Appium extension registry size is invalid")
    source_driver = str(
        appium_home / "node_modules/appium-xcuitest-driver"
    ).encode("utf-8")
    destination_driver = str(
        destination / "appium/node_modules/appium-xcuitest-driver"
    ).encode("utf-8")
    if contents.count(source_driver) != 1:
        fail("Appium extension registry does not bind the staged XCUITest driver")
    template.write_bytes(contents.replace(source_driver, destination_driver))
    template.chmod(0o600)
    manifest.unlink()
    manifest.with_name("package.hash").unlink(missing_ok=True)
    try:
        manifest.parent.rmdir()
        manifest.parent.parent.rmdir()
    except OSError:
        pass


def validate_appium_extension_template(runtime_root: Path) -> Path:
    template = runtime_root / APPIUM_EXTENSION_TEMPLATE
    if template.is_symlink() or not template.is_file():
        fail("installed runtime has no Appium extension registry template")
    contents = template.read_bytes()
    expected_path = str(
        runtime_root / "appium/node_modules/appium-xcuitest-driver"
    ).encode("utf-8")
    expected_version = load_lock(runtime_root / "toolchain.lock.json")["appium"][
        "drivers"
    ]["xcuitest"]["version"].encode("ascii")
    if (not 0 < len(contents) <= MAX_APPIUM_EXTENSION_BYTES
            or contents.count(expected_path) != 1
            or b"xcuitest:" not in contents
            or b"appium-xcuitest-driver" not in contents
            or b"version: " + expected_version not in contents):
        fail("installed Appium extension registry is not pinned to this runtime")
    return template


def resolve_runtime(appium_home: Path) -> tuple[Path, Path]:
    lock = load_lock()
    _appium_entry, tunnel_script = validate_appium_project(appium_home, lock)
    node = Path(shutil.which("node") or "")
    if not node.is_file():
        fail("Node.js is unavailable")
    expected_node = lock["appium"]["runtime"]["node"]
    version = subprocess.run(
        [str(node), "--version"], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=10, check=False,
    )
    if version.returncode or version.stdout.strip().removeprefix("v") != expected_node:
        fail("installed Node.js does not match the toolchain lock")
    return node.resolve(), tunnel_script.resolve()


def preflight(appium_home: Path) -> tuple[Path, Path]:
    node, script = resolve_runtime(appium_home)
    if not Path("/dev/net/tun").exists():
        fail("/dev/net/tun is unavailable")
    return node, script


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    """Hash an ordinary, symlink-free npm tree, excluding unused .bin links."""
    digest = hashlib.sha256()
    if not root.is_dir() or root.is_symlink():
        fail("Appium node_modules is not a safe directory")
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if ".bin" in relative.parts:
            continue
        value = path.lstat()
        if stat.S_ISLNK(value.st_mode):
            fail("Appium runtime contains an unsupported symbolic link")
        encoded = relative.as_posix().encode("utf-8")
        if stat.S_ISDIR(value.st_mode):
            digest.update(b"D\0" + encoded + b"\0")
        elif stat.S_ISREG(value.st_mode):
            digest.update(b"F\0" + encoded + b"\0")
            digest.update(b"X" if value.st_mode & 0o111 else b"-")
            digest.update(bytes.fromhex(file_sha256(path)))
        else:
            fail("Appium runtime contains an unsupported special file")
    return digest.hexdigest()


def harden_tree(root: Path, executables: set[Path]) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        value = path.lstat()
        if stat.S_ISLNK(value.st_mode):
            fail("service runtime contains a symbolic link")
        if stat.S_ISDIR(value.st_mode):
            path.chmod(0o555)
        elif stat.S_ISREG(value.st_mode):
            path.chmod(0o555 if path in executables or value.st_mode & 0o111 else 0o444)
        else:
            fail("service runtime contains a special file")
    root.chmod(0o555)


def copy_plain_tree(source: Path, destination: Path) -> None:
    """Copy bytes and executable state without source xattrs, ACLs, or ownership."""
    if not source.is_dir() or source.is_symlink() or destination.exists():
        fail("Appium runtime copy paths are unsafe")
    destination.mkdir(mode=0o700)
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(source)
        if ".bin" in relative.parts:
            continue
        value = path.lstat()
        target = destination / relative
        if stat.S_ISLNK(value.st_mode):
            fail("Appium runtime contains an unsupported symbolic link")
        if stat.S_ISDIR(value.st_mode):
            target.mkdir(mode=0o700)
        elif stat.S_ISREG(value.st_mode):
            shutil.copyfile(path, target)
            target.chmod(0o700 if value.st_mode & 0o111 else 0o600)
        else:
            fail("Appium runtime contains an unsupported special file")


def require_immutable_tree(root: Path, owner_uid: int = 0) -> None:
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        fail("installed service runtime is not a safe absolute directory")
    for path in (root, *root.rglob("*")):
        value = path.lstat()
        if stat.S_ISLNK(value.st_mode):
            fail("installed service runtime contains a symbolic link")
        if value.st_uid != owner_uid:
            fail("installed service runtime is not owned by root")
        if value.st_mode & 0o222:
            fail("installed service runtime is writable")
        if not (stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode)):
            fail("installed service runtime contains a special file")


def service_runtime_path(service_root: Path = SERVICE_ROOT, lock: dict | None = None) -> Path:
    value = lock or load_lock()
    runtime = remote_xpc_lock(value)
    return service_root / f"{runtime['version']}-r{service_runtime_revision(value)}"


def default_service_runtime() -> Path:
    """Use this version directory when running from the installed wrapper."""
    wrapper_parent = Path(__file__).resolve().parent
    if ((wrapper_parent / RUNTIME_MARKER).is_file()
            and (wrapper_parent / "toolchain.lock.json").is_file()):
        return wrapper_parent
    return service_runtime_path()


def visible_root_owner_uid(root: Path = Path("/"),
                           overflow_uid_file: Path = OVERFLOW_UID_FILE) -> int:
    """Resolve host-root ownership in direct and unprivileged user namespaces."""
    value = root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(value.st_mode):
        fail("visible filesystem root is unsafe")
    if value.st_uid == 0:
        return 0
    try:
        overflow_uid = int(overflow_uid_file.read_text(encoding="ascii").strip())
    except (OSError, UnicodeError, ValueError):
        fail("kernel overflow uid is unavailable")
    if value.st_uid != overflow_uid:
        fail("visible filesystem root has an unexpected owner")
    return overflow_uid


def require_trusted_runtime_path(runtime_root: Path, owner_uid: int) -> None:
    expected = service_runtime_path()
    if (not runtime_root.is_absolute() or runtime_root != expected
            or runtime_root.resolve() != runtime_root):
        fail("service runtime is not the exact locked system path")
    for path in SYSTEM_RUNTIME_PARENT_CHAIN:
        try:
            value = path.lstat()
        except OSError:
            fail("service runtime parent chain is unavailable")
        if (path.is_symlink() or not stat.S_ISDIR(value.st_mode)
                or value.st_uid != owner_uid or value.st_mode & 0o022):
            fail("service runtime parent chain is not root-owned and protected")


def visible_system_root_owner_uid(runtime_root: Path) -> int:
    owner_uid = visible_root_owner_uid()
    if owner_uid != 0 and owner_uid == os.geteuid():
        fail("service runtime appears to be owned by the unprivileged caller")
    require_trusted_runtime_path(runtime_root, owner_uid)
    return owner_uid


def verify_service_runtime(runtime_root: Path,
                           owner_uid: int | None = None) -> tuple[Path, Path]:
    if owner_uid is None:
        owner_uid = visible_system_root_owner_uid(runtime_root)
    require_immutable_tree(runtime_root, owner_uid)
    local_lock = load_lock(runtime_root / "toolchain.lock.json")
    runtime = remote_xpc_lock(local_lock)
    revision = service_runtime_revision(local_lock)
    if runtime_root.name != f"{runtime['version']}-r{revision}":
        fail("installed service runtime path does not match its locked revision")
    try:
        marker = json.loads((runtime_root / RUNTIME_MARKER).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("installed service runtime has no valid installation marker")
    appium_tree_sha256 = tree_sha256(runtime_root / "appium")
    if marker != {
        "schemaVersion": 1,
        "serviceRuntimeRevision": revision,
        "package": runtime["package"],
        "version": runtime["version"],
        "nodeSha256": file_sha256(runtime_root / "bin/node"),
        "wrapperSha256": file_sha256(runtime_root / "remotexpc_tunnel.py"),
        "devicePreflightSha256": file_sha256(
            runtime_root / DEVICE_PREFLIGHT_FILE.name
        ),
        "deviceInstallSha256": file_sha256(runtime_root / DEVICE_INSTALL_FILE.name),
        "deviceDdiSha256": file_sha256(runtime_root / DEVICE_DDI_FILE.name),
        "artifactTreeSha256": file_sha256(runtime_root / ARTIFACT_TREE_FILE.name),
        "lockSha256": file_sha256(runtime_root / "toolchain.lock.json"),
        "packageJsonSha256": file_sha256(runtime_root / "package.json"),
        "packageLockSha256": file_sha256(runtime_root / "package-lock.json"),
        "appiumExtensionsSha256": file_sha256(
            runtime_root / APPIUM_EXTENSION_TEMPLATE
        ),
        "appiumTreeSha256": appium_tree_sha256,
    }:
        fail("installed service runtime marker does not match its contents")
    appium_entry, script = validate_appium_project(runtime_root / "appium", local_lock)
    wrapper = runtime_root / "remotexpc_tunnel.py"
    node = runtime_root / "bin/node"
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        fail("installed service wrapper is unavailable")
    if not node.is_file() or not os.access(node, os.X_OK):
        fail("installed service Node.js is unavailable")
    if not appium_entry.is_file():
        fail("installed Appium server entry is unavailable")
    validate_appium_extension_template(runtime_root)
    return node, script


def restore_security_context(runtime_root: Path, *, owner_uid: int = 0) -> None:
    """Apply the host SELinux file policy without changing runtime bytes or modes."""
    if os.geteuid() != owner_uid or not SELINUX_ENFORCE_FILE.is_file():
        return
    restorecon = next((path for path in RESTORECON_CANDIDATES if path.is_file()), None)
    if restorecon is None:
        fail("SELinux is enabled but the trusted restorecon tool is unavailable")
    executable = restorecon.resolve()
    value = executable.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != owner_uid
            or value.st_mode & 0o022 or not value.st_mode & 0o111):
        fail("SELinux restorecon tool is not root-owned and protected")
    result = subprocess.run(
        [str(restorecon), "-RF", "--", str(runtime_root)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=120, check=False,
    )
    if result.returncode:
        fail("installed service runtime failed host security-context restoration")


def verify_runtime_matches_source(runtime_root: Path, node: Path,
                                  appium_tree_sha256: str) -> None:
    try:
        marker = json.loads((runtime_root / RUNTIME_MARKER).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("installed service runtime has no valid installation marker")
    expected = {
        "serviceRuntimeRevision": service_runtime_revision(load_lock()),
        "nodeSha256": file_sha256(node),
        "wrapperSha256": file_sha256(Path(__file__).resolve()),
        "devicePreflightSha256": file_sha256(DEVICE_PREFLIGHT_FILE),
        "deviceInstallSha256": file_sha256(DEVICE_INSTALL_FILE),
        "deviceDdiSha256": file_sha256(DEVICE_DDI_FILE),
        "artifactTreeSha256": file_sha256(ARTIFACT_TREE_FILE),
        "lockSha256": file_sha256(LOCK_FILE),
        "packageJsonSha256": file_sha256(PACKAGE_FILE),
        "packageLockSha256": file_sha256(NPM_LOCK_FILE),
        "appiumTreeSha256": appium_tree_sha256,
    }
    if any(marker.get(key) != value for key, value in expected.items()):
        fail("existing immutable service runtime differs from the audited source")


def install_service_runtime(appium_home: Path, service_root: Path = SERVICE_ROOT) -> Path:
    """Create an immutable version directory and never update it in place."""
    lock = load_lock()
    runtime = remote_xpc_lock(lock)
    node, _script = resolve_runtime(appium_home)
    validate_appium_project(appium_home, lock)
    source_digest = tree_sha256(appium_home)

    if not service_root.is_absolute() or service_root.is_symlink():
        fail("service root must be a safe absolute directory")
    if service_root.exists():
        root_stat = service_root.lstat()
        if (not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.geteuid()
                or root_stat.st_mode & 0o022):
            fail("service root is not a private root-owned directory")
    else:
        service_root.mkdir(parents=True, mode=0o755)
    destination = service_runtime_path(service_root, lock)
    if destination.exists() or destination.is_symlink():
        verify_service_runtime(destination, os.geteuid())
        verify_runtime_matches_source(destination, node, source_digest)
        restore_security_context(destination)
        verify_service_runtime(destination, os.geteuid())
        return destination

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=service_root))
    try:
        (staging / "bin").mkdir()
        shutil.copyfile(Path(__file__).resolve(), staging / "remotexpc_tunnel.py")
        shutil.copyfile(DEVICE_PREFLIGHT_FILE, staging / DEVICE_PREFLIGHT_FILE.name)
        shutil.copyfile(DEVICE_INSTALL_FILE, staging / DEVICE_INSTALL_FILE.name)
        shutil.copyfile(DEVICE_DDI_FILE, staging / DEVICE_DDI_FILE.name)
        shutil.copyfile(ARTIFACT_TREE_FILE, staging / ARTIFACT_TREE_FILE.name)
        shutil.copyfile(LOCK_FILE, staging / "toolchain.lock.json")
        shutil.copyfile(PACKAGE_FILE, staging / "package.json")
        shutil.copyfile(NPM_LOCK_FILE, staging / "package-lock.json")
        shutil.copyfile(node, staging / "bin/node")
        (staging / "bin/node").chmod(0o700)
        copy_plain_tree(appium_home, staging / "appium")
        copied_digest = tree_sha256(staging / "appium")
        if copied_digest != source_digest or tree_sha256(appium_home) != source_digest:
            fail("Appium runtime changed while its service copy was created")
        validate_appium_project(staging / "appium", load_lock(staging / "toolchain.lock.json"))
        prepare_appium_extension_template(
            staging / "appium", staging / "bin/node", destination,
            staging / APPIUM_EXTENSION_TEMPLATE,
        )
        copied_digest = tree_sha256(staging / "appium")
        marker = {
            "schemaVersion": 1,
            "serviceRuntimeRevision": service_runtime_revision(lock),
            "package": runtime["package"],
            "version": runtime["version"],
            "nodeSha256": file_sha256(staging / "bin/node"),
            "wrapperSha256": file_sha256(staging / "remotexpc_tunnel.py"),
            "devicePreflightSha256": file_sha256(
                staging / DEVICE_PREFLIGHT_FILE.name
            ),
            "deviceInstallSha256": file_sha256(staging / DEVICE_INSTALL_FILE.name),
            "deviceDdiSha256": file_sha256(staging / DEVICE_DDI_FILE.name),
            "artifactTreeSha256": file_sha256(staging / ARTIFACT_TREE_FILE.name),
            "lockSha256": file_sha256(staging / "toolchain.lock.json"),
            "packageJsonSha256": file_sha256(staging / "package.json"),
            "packageLockSha256": file_sha256(staging / "package-lock.json"),
            "appiumExtensionsSha256": file_sha256(
                staging / APPIUM_EXTENSION_TEMPLATE
            ),
            "appiumTreeSha256": copied_digest,
        }
        (staging / RUNTIME_MARKER).write_text(
            json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        harden_tree(staging, {staging / "bin/node", staging / "remotexpc_tunnel.py"})
        staging.replace(destination)
        restore_security_context(destination)
    except BaseException:
        if staging.exists():
            for path in sorted(
                    (staging, *staging.rglob("*")), key=lambda item: len(item.parts), reverse=True):
                try:
                    if path.is_dir():
                        path.chmod(0o700)
                    else:
                        path.chmod(0o600)
                except OSError:
                    pass
            shutil.rmtree(staging, ignore_errors=True)
        raise
    verify_service_runtime(destination, os.geteuid())
    return destination


def serve(arguments: argparse.Namespace) -> int:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        fail("RemoteXPC tunnel service is supported only on Linux")
    if os.geteuid() != 0:
        fail("RemoteXPC tunnel creation must run as root")
    node, script = verify_service_runtime(arguments.service_runtime)
    if not Path("/dev/net/tun").exists():
        fail("/dev/net/tun is unavailable")
    command = [
        str(node), str(script),
        "--tunnel-registry-port", str(arguments.port),
        "--reconnect-retries", "3",
    ]
    child = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    def forward_signal(signum, _frame):
        if child.poll() is None:
            child.send_signal(signum)

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)
    tokens = private_device_tokens()
    assert child.stdout is not None
    for line in child.stdout:
        print(redact(line.rstrip("\n"), tokens), flush=True)
    return child.wait()


def status(arguments: argparse.Namespace) -> int:
    verify_service_runtime(arguments.service_runtime)
    verify_installed_unit(arguments.service_runtime, arguments.port)
    try:
        with urlopen(
            f"http://127.0.0.1:{arguments.port}/remotexpc/tunnels/metadata", timeout=3
        ) as response:
            payload = response.read(64 * 1024 + 1)
            if len(payload) > 64 * 1024:
                fail("RemoteXPC registry response exceeded the safety limit")
            value = json.loads(payload)
    except (OSError, URLError, json.JSONDecodeError):
        print("remotexpc=offline tunnels=unknown")
        return 1
    active = value.get("activeTunnels") if isinstance(value, dict) else None
    if not isinstance(active, int) or active < 0:
        fail("RemoteXPC registry returned invalid metadata")
    print(f"remotexpc=online tunnels={active}")
    return 0 if active > 0 else 2


def systemd_quote(value: object) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def service_unit(runtime_root: Path, port: int) -> str:
    wrapper = runtime_root / "remotexpc_tunnel.py"
    command = " ".join(map(systemd_quote, (
        wrapper, "serve", "--service-runtime", runtime_root, "--port", port,
    )))
    return f"""[Unit]
Description=Overte Fedora iOS RemoteXPC tunnel registry
After=network.target usbmuxd.service
Wants=usbmuxd.service
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart={command}
WorkingDirectory={runtime_root}
Restart=on-failure
RestartSec=5
Environment=PATH={systemd_quote(str(runtime_root / "bin") + ":/usr/sbin:/usr/bin")}
Environment=XDG_DATA_HOME={systemd_quote(SERVICE_STATE_ROOT)}
StateDirectory={SERVICE_STATE_DIRECTORY}
StateDirectoryMode=0700
UMask=0077
NoNewPrivileges=true
CapabilityBoundingSet=CAP_NET_ADMIN
AmbientCapabilities=CAP_NET_ADMIN
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
RestrictSUIDSGID=true
LockPersonality=true
RestrictNamespaces=true
SystemCallArchitectures=native

[Install]
WantedBy=multi-user.target
"""


def require_private_state_root(path: Path) -> None:
    if (not path.is_absolute() or path.is_symlink() or not path.is_dir()
            or path.resolve() != path):
        fail("Appium state root must be a safe absolute directory")
    value = path.lstat()
    if value.st_uid != os.geteuid() or value.st_mode & 0o077:
        fail("Appium state root must be owned by the caller with mode 0700")


def require_private_regular_file(path: Path, label: str, maximum: int) -> Path:
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.resolve() != path):
        fail(f"{label} is not a safe absolute private file")
    value = path.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != os.geteuid()
            or value.st_nlink != 1 or stat.S_IMODE(value.st_mode) != 0o600
            or not 0 < value.st_size <= maximum):
        fail(f"{label} ownership, mode, link count, or size is invalid")
    parent = path.parent.lstat()
    if (parent.st_uid != os.geteuid() or parent.st_mode & 0o077):
        fail(f"{label} parent directory is not caller-private")
    return path


def file_sha384(path: Path) -> str:
    digest = hashlib.sha384()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_developer_disk_image(request: dict, lock: dict) -> tuple[Path, Path, Path]:
    """Bind an operator-supplied private DDI to the exact offline lock."""
    try:
        ddi = lock["developerDiskImage"]
        provenance = ddi["provenance"]
        files = ddi["files"]
    except (KeyError, TypeError):
        fail("Developer Disk Image lock is unavailable")
    paths = {
        "Image.dmg": Path(request["image"]),
        "BuildManifest.plist": Path(request["manifest"]),
        "Image.dmg.trustcache": Path(request["trustcache"]),
    }
    parents = set()
    for name, path in paths.items():
        expected = files.get(name)
        if (path.name != name or not isinstance(expected, dict)
                or isinstance(expected.get("size"), bool)
                or not isinstance(expected.get("size"), int)
                or expected["size"] <= 0
                or not isinstance(expected.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"])):
            fail("private Developer Disk Image request differs from its lock")
        require_private_regular_file(path, f"Developer Disk Image {name}", expected["size"])
        if path.stat().st_size != expected["size"] or file_sha256(path) != expected["sha256"]:
            fail("private Developer Disk Image payload differs from its lock")
        parents.add(path.parent.resolve())
    if len(parents) != 1:
        fail("private Developer Disk Image files are not colocated")
    parent = next(iter(parents))
    parent_value = parent.lstat()
    if (not stat.S_ISDIR(parent_value.st_mode) or parent_value.st_uid != os.geteuid()
            or stat.S_IMODE(parent_value.st_mode) != 0o700):
        fail("private Developer Disk Image directory is not mode 0700")

    image = paths["Image.dmg"]
    trustcache = paths["Image.dmg.trustcache"]
    manifest_path = paths["BuildManifest.plist"]
    for name, path in (("Image.dmg", image), ("Image.dmg.trustcache", trustcache)):
        expected_sha1 = files[name].get("sha1")
        expected_sha384 = files[name].get("sha384")
        if (not isinstance(expected_sha1, str)
                or not re.fullmatch(r"[0-9a-f]{40}", expected_sha1)
                or file_sha1(path) != expected_sha1
                or not isinstance(expected_sha384, str)
                or not re.fullmatch(r"[0-9a-f]{96}", expected_sha384)
                or file_sha384(path) != expected_sha384):
            fail("private Developer Disk Image manifest digest differs from its lock")
    try:
        manifest = plistlib.loads(manifest_path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        fail("private Developer Disk Image manifest is invalid")
    if not isinstance(manifest, dict):
        fail("private Developer Disk Image manifest is invalid")
    identities = manifest.get("BuildIdentities")
    if (manifest.get("ProductBuildVersion") != provenance.get("productBuildVersion")
            or not isinstance(identities, list) or not identities):
        fail("private Developer Disk Image build manifest differs from its lock")
    image_digest = bytes.fromhex(files["Image.dmg"]["sha384"])
    trustcache_digest = bytes.fromhex(files["Image.dmg.trustcache"]["sha384"])
    image_sha1 = bytes.fromhex(files["Image.dmg"]["sha1"])
    trustcache_sha1 = bytes.fromhex(files["Image.dmg.trustcache"]["sha1"])
    bound_identities = 0
    for identity in identities:
        entries = identity.get("Manifest") if isinstance(identity, dict) else None
        personalized = entries.get("PersonalizedDMG") if isinstance(entries, dict) else None
        trust = entries.get("LoadableTrustCache") if isinstance(entries, dict) else None
        image_info = personalized.get("Info") if isinstance(personalized, dict) else None
        trust_info = trust.get("Info") if isinstance(trust, dict) else None
        if personalized is None and trust is None:
            continue
        hash_method = image_info.get("HashMethod") if isinstance(image_info, dict) else None
        expected_image = image_digest if hash_method == "sha2-384" else image_sha1
        expected_trust = trustcache_digest if hash_method == "sha2-384" else trustcache_sha1
        if (hash_method not in {"sha1", "sha2-384"}
                or not isinstance(image_info, dict) or not isinstance(trust_info, dict)
                or image_info.get("Path") != "Image.dmg"
                or personalized.get("Digest") != expected_image
                or trust_info.get("Path") != "Image.dmg.trustcache"
                or trust.get("Digest") != expected_trust):
            fail("private Developer Disk Image manifest payload binding is invalid")
        bound_identities += 1
    if bound_identities == 0:
        fail("private Developer Disk Image manifest contains no payload bindings")
    return image, manifest_path, trustcache


def device_ddi(arguments: argparse.Namespace) -> int:
    """Mount/attest the exact private DDI without logging its device binding."""
    try:
        node, _script = verify_service_runtime(arguments.service_runtime)
        payload = sys.stdin.buffer.read(16 * 1024 + 1)
        if len(payload) > 16 * 1024:
            fail("private Developer Disk Image request exceeded its safety limit")
        request = json.loads(payload)
        expected_keys = {"udid"} if arguments.action == "device-ddi-status" else {
            "udid", "image", "manifest", "trustcache",
        }
        if (not isinstance(request, dict) or set(request) != expected_keys
                or not isinstance(request.get("udid"), str)
                or not 8 <= len(request["udid"]) <= 128
                or any(character in request["udid"] for character in "\0\r\n")):
            fail("private Developer Disk Image request is invalid")
        lock = load_lock(arguments.service_runtime / "toolchain.lock.json")
        helper_request = {
            "action": "status" if arguments.action == "device-ddi-status" else "mount",
            "udid": request["udid"],
            "imageSha384": lock["developerDiskImage"]["files"]["Image.dmg"]["sha384"],
        }
        validated_files = None
        if arguments.action == "device-ddi-mount":
            validated_files = validate_developer_disk_image(request, lock)
        with tempfile.TemporaryDirectory(prefix="overte-ios-ddi-") as name:
            temporary = Path(name)
            if validated_files is not None:
                snapshot = temporary / "ddi"
                snapshot.mkdir(mode=0o700)
                for source in validated_files:
                    destination = snapshot / source.name
                    shutil.copyfile(source, destination)
                    destination.chmod(0o600)
                image, manifest, trustcache = validate_developer_disk_image({
                    "image": str(snapshot / "Image.dmg"),
                    "manifest": str(snapshot / "BuildManifest.plist"),
                    "trustcache": str(snapshot / "Image.dmg.trustcache"),
                }, lock)
                helper_request.update({
                    "image": str(image), "manifest": str(manifest),
                    "trustcache": str(trustcache),
                })
            data_home = temporary / "data"
            data_home.mkdir(mode=0o700)
            port_file = data_home / TUNNEL_PORT_ITEM
            port_file.parent.mkdir(parents=True, mode=0o700)
            descriptor = os.open(
                port_file,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="ascii") as output:
                output.write(str(arguments.port))
                output.flush()
                os.fsync(output.fileno())
            environment = {
                "PATH": str(arguments.service_runtime / "bin") + ":/usr/sbin:/usr/bin",
                "HOME": "/nonexistent",
                "XDG_DATA_HOME": str(data_home),
            }
            result = subprocess.run(
                [str(node), str(arguments.service_runtime / DEVICE_DDI_FILE.name)],
                input=json.dumps(helper_request, separators=(",", ":")).encode("utf-8"),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=arguments.service_runtime, env=environment,
                timeout=5 * 60 if arguments.action == "device-ddi-mount" else 60,
                check=False,
            )
        if result.returncode:
            fail("private Developer Disk Image helper failed")
    except (TunnelError, OSError, UnicodeError, json.JSONDecodeError,
            plistlib.InvalidFileException, subprocess.SubprocessError, KeyError, TypeError):
        fail("private iOS Developer Disk Image request failed")
    print("PASS: iOS Personalized DDI and XCTest services are ready")
    return 0


def parse_receipt_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        fail(f"signed receipt {label} is invalid")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        fail(f"signed receipt {label} is invalid")


def validate_install_receipt(path: Path) -> dict:
    require_private_regular_file(path, "signed receipt", MAX_RECEIPT_BYTES)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("signed receipt is unreadable")
    expected = {
        "schemaVersion", "contract", "sourceRevision", "createdAt", "notAfter",
        "provenance", "overte", "wda", "toolchain",
    }
    if (not isinstance(receipt, dict) or set(receipt) != expected
            or receipt.get("schemaVersion") != 1
            or receipt.get("contract") not in {PROTECTED_RECEIPT, PERSONAL_RECEIPT}
            or not isinstance(receipt.get("sourceRevision"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", receipt["sourceRevision"])):
        fail("signed receipt contract is invalid")
    created = parse_receipt_time(receipt["createdAt"], "createdAt")
    not_after = parse_receipt_time(receipt["notAfter"], "notAfter")
    now = datetime.now(timezone.utc)
    maximum = timedelta(hours=24) if receipt["contract"] == PROTECTED_RECEIPT \
        else timedelta(days=7)
    if (created > now + timedelta(minutes=5) or not_after <= now
            or not_after <= created or not_after > created + maximum):
        fail("signed receipt validity window is invalid or expired")
    if receipt["contract"] == PROTECTED_RECEIPT \
            and not_after != created + timedelta(hours=24):
        fail("protected signed receipt validity window is not exactly 24 hours")
    expected_toolchain = {
        "xcuitestDriver": "12.8.0", "remoteXpc": "5.15.3",
        "webdriverAgent": "16.8.0",
    }
    if receipt["toolchain"] != expected_toolchain:
        fail("signed receipt toolchain differs from the immutable runtime")
    provenance = receipt["provenance"]
    if receipt["contract"] == PROTECTED_RECEIPT:
        if (not isinstance(provenance, dict) or set(provenance) != {
                "repository", "repositoryId", "workflow", "reusableWorkflow", "ref",
                "runId", "runAttempt"}
                or provenance.get("workflow") != ".github/workflows/ios-bootstrap.yml"
                or provenance.get("reusableWorkflow")
                != ".github/workflows/ios-fedora-e2e-producer.yml"
                or provenance.get("ref") != "refs/heads/apple-ios"
                or provenance.get("repository") != "noah-be/overte"
                or any(isinstance(provenance.get(key), bool)
                       or not isinstance(provenance.get(key), int)
                       or provenance[key] <= 0
                       for key in ("repositoryId", "runId", "runAttempt"))):
            fail("protected signed receipt provenance is invalid")
    elif (not isinstance(provenance, dict) or set(provenance) != {
            "mode", "unsignedKitContract", "unsignedKitManifestSha256",
            "attestationContract", "derivationBinding"}
            or provenance.get("mode") != "personal-team-manual-signing"
            or provenance.get("unsignedKitContract")
            != "overte-ios-personal-team-e2e-kit-v3"
            or provenance.get("attestationContract")
            != "overte-ios-personal-team-signed-handoff-v1"
            or provenance.get("derivationBinding") != "human-verified"
            or not isinstance(provenance.get("unsignedKitManifestSha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", provenance["unsignedKitManifestSha256"])):
        fail("Personal-Team signed receipt provenance is invalid")

    overte = receipt["overte"]
    wda = receipt["wda"]
    if (not isinstance(overte, dict)
            or set(overte) != {"path", "sha256", "bundleId"}
            or overte.get("bundleId") != OVERTE_BUNDLE_ID
            or not isinstance(overte.get("path"), str)
            or not isinstance(overte.get("sha256"), str)
            or not isinstance(wda, dict)
            or set(wda) != {
                "ipaPath", "ipaSha256", "prebuiltPath", "prebuiltTreeSha256",
                "bundleId"}
            or wda.get("bundleId") != WDA_BUNDLE_ID
            or not isinstance(wda.get("ipaPath"), str)
            or not isinstance(wda.get("ipaSha256"), str)
            or not isinstance(wda.get("prebuiltPath"), str)
            or not isinstance(wda.get("prebuiltTreeSha256"), str)):
        fail("signed receipt app inventory is invalid")
    receipt_parent = path.parent.resolve()
    overte_path = Path(overte["path"])
    wda_path = Path(wda["ipaPath"])
    prebuilt_path = Path(wda["prebuiltPath"])
    for artifact, digest, label in (
            (overte_path, overte.get("sha256"), "Overte IPA"),
            (wda_path, wda.get("ipaSha256"), "WDA IPA")):
        require_private_regular_file(artifact, label, MAX_IPA_BYTES)
        if artifact.parent.resolve() != receipt_parent:
            fail(f"{label} is not colocated with its receipt")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) \
                or file_sha256(artifact) != digest:
            fail(f"{label} digest differs from its receipt")
    if prebuilt_path.parent.resolve() != receipt_parent:
        fail("prebuilt WDA is not colocated with its receipt")
    expected_tree = wda.get("prebuiltTreeSha256")
    if not isinstance(expected_tree, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_tree):
        fail("prebuilt WDA digest is invalid")
    try:
        actual_tree = artifact_tree_sha256(
            prebuilt_path, owner_uid=os.geteuid(), require_private=True,
        )
    except ArtifactTreeError as error:
        fail(str(error))
    if actual_tree != expected_tree:
        fail("prebuilt WDA tree differs from its receipt")
    return receipt


def device_install(arguments: argparse.Namespace) -> int:
    try:
        node, _script = verify_service_runtime(arguments.service_runtime)
        payload = sys.stdin.buffer.read(8193)
        if len(payload) > 8192:
            fail("private device install request exceeded its safety limit")
        request = json.loads(payload)
        if (not isinstance(request, dict) or set(request) != {"udid", "receipt"}
                or not isinstance(request["udid"], str)
                or not 8 <= len(request["udid"]) <= 128
                or any(character in request["udid"] for character in "\0\r\n")
                or not isinstance(request["receipt"], str)
                or any(character in request["receipt"] for character in "\0\r\n")):
            fail("private device install request is invalid")
        receipt = validate_install_receipt(Path(request["receipt"]))
        helper_payload = json.dumps({
            "udid": request["udid"],
            "overteIpa": receipt["overte"]["path"],
            "wdaIpa": receipt["wda"]["ipaPath"],
        }, separators=(",", ":")).encode("utf-8")
        environment = {
            "PATH": str(arguments.service_runtime / "bin") + ":/usr/sbin:/usr/bin",
            "HOME": "/nonexistent",
        }
        result = subprocess.run(
            [str(node), str(arguments.service_runtime / DEVICE_INSTALL_FILE.name)],
            input=helper_payload, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=arguments.service_runtime, env=environment, timeout=20 * 60, check=False,
        )
        if result.returncode:
            fail("immutable iOS installation-proxy helper failed")
    except (TunnelError, OSError, UnicodeError, json.JSONDecodeError,
            subprocess.SubprocessError, ArtifactTreeError):
        fail("signed iOS app installation request failed")
    print("PASS: receipt-bound signed iOS apps installed")
    return 0


def device_preflight(arguments: argparse.Namespace) -> int:
    node, _script = verify_service_runtime(arguments.service_runtime)
    payload = sys.stdin.buffer.read(4097)
    if len(payload) > 4096:
        fail("private device preflight request exceeded its safety limit")
    try:
        request = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError):
        fail("private device preflight request is invalid")
    keys = set(request) if isinstance(request, dict) else set()
    legacy = keys == {"udid"}
    discovery = (keys == {"udid", "discoverRemappedBundleIds"}
                 and request.get("discoverRemappedBundleIds") is True)
    exact = keys == {"udid", "overteBundleId", "wdaBundleId"}
    if (not isinstance(request, dict) or not (legacy or discovery or exact)
            or not isinstance(request.get("udid"), str)
            or not 8 <= len(request["udid"]) <= 128
            or any(character in request["udid"] for character in "\0\r\n")):
        fail("private device preflight request is invalid")
    if exact:
        identifiers = (request.get("overteBundleId"), request.get("wdaBundleId"))
        if (identifiers[0] == identifiers[1]
                or any(not isinstance(value, str) or len(value) > 255
                       or not BUNDLE_ID_RE.fullmatch(value) for value in identifiers)):
            fail("private device preflight request is invalid")
    helper = arguments.service_runtime / DEVICE_PREFLIGHT_FILE.name
    environment = {
        "PATH": str(arguments.service_runtime / "bin") + ":/usr/sbin:/usr/bin",
        "HOME": "/nonexistent",
    }
    result = subprocess.run(
        [str(node), str(helper)], input=payload, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, cwd=arguments.service_runtime,
        env=environment, timeout=60, check=False,
    )
    if result.returncode:
        fail("installed iOS app preflight failed")
    if discovery:
        if len(result.stdout) > 4096:
            fail("installed iOS app discovery response exceeded its safety limit")
        try:
            inventory = json.loads(result.stdout)
        except (UnicodeError, json.JSONDecodeError):
            fail("installed iOS app discovery response is invalid")
        if not isinstance(inventory, dict) or set(inventory) != {
                "overteBundleId", "wdaBundleId", "wdaUpdatedBundleId",
                "wdaBundleIdSuffix"}:
            fail("installed iOS app discovery response is invalid")
        bundle_values = (
            inventory.get("overteBundleId"), inventory.get("wdaBundleId"),
            inventory.get("wdaUpdatedBundleId"),
        )
        suffix = inventory.get("wdaBundleIdSuffix")
        if (bundle_values[0] == bundle_values[1]
                or any(not isinstance(value, str) or len(value) > 255
                       or not BUNDLE_ID_RE.fullmatch(value) for value in bundle_values)
                or suffix not in {"", ".xctrunner"}
                or bundle_values[2] + suffix != bundle_values[1]):
            fail("installed iOS app discovery response is invalid")
        print(json.dumps(inventory, sort_keys=True, separators=(",", ":")))
        return 0
    print("PASS: installed iOS app contracts verified")
    return 0


def appium_server(arguments: argparse.Namespace) -> int:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        fail("immutable Appium server entry is supported only on Linux")
    node, _script = verify_service_runtime(arguments.service_runtime)
    appium_entry = arguments.service_runtime / "appium/node_modules/appium/build/lib/main.js"
    if arguments.address not in {"127.0.0.1", "::1"}:
        fail("Appium server must bind only to loopback")
    require_private_state_root(arguments.state_root)
    template = validate_appium_extension_template(arguments.service_runtime)
    temporary = Path(tempfile.mkdtemp(prefix="appium-home-", dir=arguments.state_root))
    temporary.chmod(0o700)
    try:
        appium_home = temporary / "home"
        appium_home.mkdir(mode=0o700)
        data_home = temporary / "data"
        data_home.mkdir(mode=0o700)
        registry_port_file = data_home / TUNNEL_PORT_ITEM
        registry_port_file.parent.mkdir(parents=True, mode=0o700)
        descriptor = os.open(
            registry_port_file,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="ascii") as output:
            output.write(str(arguments.tunnel_registry_port))
            output.flush()
            os.fsync(output.fileno())
        node_modules = appium_home / "node_modules"
        node_modules.mkdir(mode=0o700)
        cache_parent = node_modules / ".cache"
        cache_parent.mkdir(mode=0o700)
        cache = cache_parent / "appium"
        cache.mkdir(mode=0o700)
        extension_manifest = cache / "extensions.yaml"
        shutil.copyfile(template, extension_manifest)
        extension_manifest.chmod(0o600)
        environment = os.environ.copy()
        environment["APPIUM_HOME"] = str(appium_home)
        # appium-ios-remotexpc discovers the already running root service via
        # this non-secret Strongbox locator.  Never expose the root-owned
        # pairing state to the unprivileged Appium process.
        environment["XDG_DATA_HOME"] = str(data_home)
        environment["PATH"] = str(arguments.service_runtime / "bin") + ":/usr/sbin:/usr/bin"
        command = [
            str(node), str(appium_entry), "--address", arguments.address,
            "--port", str(arguments.port), "--base-path", arguments.base_path,
            "--use-drivers", "xcuitest", "--log-level", "error", "--log-no-colors",
        ]
        child = subprocess.Popen(
            command, cwd=arguments.service_runtime / "appium", env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        def forward_signal(signum, _frame):
            if child.poll() is None:
                child.send_signal(signum)

        signal.signal(signal.SIGTERM, forward_signal)
        signal.signal(signal.SIGINT, forward_signal)
        return child.wait()
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def verify_installed_unit(runtime_root: Path, port: int, unit_path: Path = UNIT_PATH,
                          owner_uid: int = 0) -> None:
    if (not unit_path.is_absolute() or unit_path.is_symlink() or not unit_path.is_file()
            or unit_path.resolve() != unit_path):
        fail("installed RemoteXPC systemd unit path is unsafe")
    value = unit_path.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != owner_uid
            or value.st_mode & 0o022):
        fail("installed RemoteXPC systemd unit is not root-owned and protected")
    if unit_path.stat().st_size > 64 * 1024 \
            or unit_path.read_text(encoding="utf-8") != service_unit(runtime_root, port):
        fail("installed RemoteXPC systemd unit does not attest the immutable runtime")
    drop_ins = unit_path.parent / f"{unit_path.name}.d"
    if drop_ins.exists() and (drop_ins.is_symlink() or not drop_ins.is_dir()
                              or any(drop_ins.iterdir())):
        fail("installed RemoteXPC systemd unit has unsupported overrides")


def activate_systemd_unit() -> None:
    subprocess.run(["systemctl", "daemon-reload"], timeout=30, check=True)
    subprocess.run(["systemctl", "reset-failed", UNIT_NAME], timeout=30, check=True)
    subprocess.run(["systemctl", "enable", UNIT_NAME], timeout=30, check=True)
    # `enable --now` does not restart an already active unit after its immutable
    # runtime path changes.  Restart explicitly so a successful installer can
    # never leave the previous version executing behind the updated unit file.
    subprocess.run(["systemctl", "restart", UNIT_NAME], timeout=60, check=True)


def install_unit(arguments: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        fail("install-unit must run as root")
    preflight(arguments.appium_home)
    runtime_root = install_service_runtime(arguments.appium_home)
    verify_service_runtime(runtime_root)
    unit = service_unit(runtime_root, arguments.port)
    destination = arguments.unit_path.resolve()
    if destination != UNIT_PATH:
        fail(f"unit path must be /etc/systemd/system/{UNIT_NAME}")
    parent = destination.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022):
        fail("systemd unit directory is not root-owned and protected")
    temporary = destination.with_suffix(".service.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as output:
            output.write(unit)
            output.flush()
            os.fsync(output.fileno())
        os.close(descriptor)
        descriptor = -1
        temporary.replace(destination)
        directory = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    verify_installed_unit(runtime_root, arguments.port)
    activate_systemd_unit()
    print(f"Installed and started {UNIT_NAME}")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    subparsers = value.add_subparsers(dest="action", required=True)
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--appium-home", type=Path, required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--service-runtime", type=Path, required=True)
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument(
        "--service-runtime", type=Path, default=default_service_runtime(),
    )
    status_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    appium_parser = subparsers.add_parser("appium-server")
    appium_parser.add_argument("--service-runtime", type=Path, default=default_service_runtime())
    appium_parser.add_argument("--address", default="127.0.0.1")
    appium_parser.add_argument("--port", type=int, default=4723)
    appium_parser.add_argument("--tunnel-registry-port", type=int, default=DEFAULT_PORT)
    appium_parser.add_argument("--base-path", choices=("/", "/wd/hub"), default="/")
    appium_parser.add_argument("--state-root", type=Path, required=True)

    pre_session_parser = subparsers.add_parser("device-preflight")
    pre_session_parser.add_argument(
        "--service-runtime", type=Path, default=default_service_runtime(),
    )

    device_install_parser = subparsers.add_parser("device-install")
    device_install_parser.add_argument(
        "--service-runtime", type=Path, default=default_service_runtime(),
    )

    for action in ("device-ddi-status", "device-ddi-mount"):
        ddi_parser = subparsers.add_parser(action)
        ddi_parser.add_argument(
            "--service-runtime", type=Path, default=default_service_runtime(),
        )
        ddi_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    install_parser = subparsers.add_parser("install-unit")
    install_parser.add_argument("--appium-home", type=Path, required=True)
    install_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    install_parser.add_argument("--unit-path", type=Path, default=UNIT_PATH)
    return value


def main() -> int:
    arguments = parser().parse_args()
    try:
        if hasattr(arguments, "port") and not 1 <= arguments.port <= 65535:
            fail("registry port must be between 1 and 65535")
        if (hasattr(arguments, "tunnel_registry_port")
                and not 1 <= arguments.tunnel_registry_port <= 65535):
            fail("tunnel registry port must be between 1 and 65535")
        if arguments.action == "preflight":
            preflight(arguments.appium_home)
            print("PASS: pinned RemoteXPC runtime and /dev/net/tun are available")
            return 0
        if arguments.action == "serve":
            return serve(arguments)
        if arguments.action == "status":
            return status(arguments)
        if arguments.action == "appium-server":
            return appium_server(arguments)
        if arguments.action == "device-preflight":
            return device_preflight(arguments)
        if arguments.action == "device-install":
            return device_install(arguments)
        if arguments.action in {"device-ddi-status", "device-ddi-mount"}:
            return device_ddi(arguments)
        return install_unit(arguments)
    except (TunnelError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
