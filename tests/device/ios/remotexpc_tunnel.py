#!/usr/bin/env python3
"""Manage the pinned, privacy-redacted RemoteXPC tunnel used by Fedora Appium."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from urllib.error import URLError
from urllib.request import urlopen


DEVICE_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = DEVICE_ROOT / "toolchain.lock.json"
DEFAULT_PORT = 42314
UNIT_NAME = "overte-ios-remotexpc.service"
SERVICE_ROOT = Path("/usr/local/lib/overte-ios-remotexpc")
UNIT_PATH = Path("/etc/systemd/system") / UNIT_NAME
RUNTIME_MARKER = "service-runtime.json"
DEVICE_TOKEN_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])[0-9a-fA-F]{24,64}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}(?![A-Za-z0-9])"),
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


def resolve_runtime(appium_home: Path) -> tuple[Path, Path]:
    lock = load_lock()
    package_root = resolve_package(appium_home / "node_modules", lock)
    tunnel_script = package_root / "scripts" / "tunnel-creation.mjs"
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
    runtime = remote_xpc_lock(lock or load_lock())
    return service_root / runtime["version"]


def default_service_runtime() -> Path:
    """Use this version directory when running from the installed wrapper."""
    wrapper_parent = Path(__file__).resolve().parent
    if ((wrapper_parent / RUNTIME_MARKER).is_file()
            and (wrapper_parent / "toolchain.lock.json").is_file()):
        return wrapper_parent
    return service_runtime_path()


def verify_service_runtime(runtime_root: Path, owner_uid: int = 0) -> tuple[Path, Path]:
    require_immutable_tree(runtime_root, owner_uid)
    local_lock = load_lock(runtime_root / "toolchain.lock.json")
    runtime = remote_xpc_lock(local_lock)
    if runtime_root.name != runtime["version"]:
        fail("installed service runtime path does not match its locked version")
    try:
        marker = json.loads((runtime_root / RUNTIME_MARKER).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("installed service runtime has no valid installation marker")
    if marker != {
        "schemaVersion": 1,
        "package": runtime["package"],
        "version": runtime["version"],
        "nodeSha256": file_sha256(runtime_root / "bin/node"),
        "wrapperSha256": file_sha256(runtime_root / "remotexpc_tunnel.py"),
        "lockSha256": file_sha256(runtime_root / "toolchain.lock.json"),
        "nodeModulesSha256": marker.get("nodeModulesSha256"),
    } or not re.fullmatch(r"[0-9a-f]{64}", marker.get("nodeModulesSha256", "")):
        fail("installed service runtime marker does not match its contents")
    package = resolve_package(runtime_root / "appium/node_modules", local_lock)
    wrapper = runtime_root / "remotexpc_tunnel.py"
    node = runtime_root / "bin/node"
    script = package / "scripts/tunnel-creation.mjs"
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        fail("installed service wrapper is unavailable")
    if not node.is_file() or not os.access(node, os.X_OK):
        fail("installed service Node.js is unavailable")
    return node, script


def install_service_runtime(appium_home: Path, service_root: Path = SERVICE_ROOT) -> Path:
    """Create an immutable version directory and never update it in place."""
    lock = load_lock()
    runtime = remote_xpc_lock(lock)
    node, _script = resolve_runtime(appium_home)
    source_modules = appium_home / "node_modules"
    source_digest = tree_sha256(source_modules)

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
        return destination

    staging = Path(tempfile.mkdtemp(prefix=f".{runtime['version']}.", dir=service_root))
    try:
        (staging / "bin").mkdir()
        (staging / "appium").mkdir()
        shutil.copy2(Path(__file__).resolve(), staging / "remotexpc_tunnel.py")
        shutil.copy2(LOCK_FILE, staging / "toolchain.lock.json")
        shutil.copy2(node, staging / "bin/node")
        shutil.copytree(
            source_modules, staging / "appium/node_modules",
            ignore=shutil.ignore_patterns(".bin"), symlinks=False,
        )
        copied_digest = tree_sha256(staging / "appium/node_modules")
        if copied_digest != source_digest or tree_sha256(source_modules) != source_digest:
            fail("Appium runtime changed while its service copy was created")
        resolve_package(staging / "appium/node_modules", load_lock(staging / "toolchain.lock.json"))
        marker = {
            "schemaVersion": 1,
            "package": runtime["package"],
            "version": runtime["version"],
            "nodeSha256": file_sha256(staging / "bin/node"),
            "wrapperSha256": file_sha256(staging / "remotexpc_tunnel.py"),
            "lockSha256": file_sha256(staging / "toolchain.lock.json"),
            "nodeModulesSha256": copied_digest,
        }
        (staging / RUNTIME_MARKER).write_text(
            json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        harden_tree(staging, {staging / "bin/node", staging / "remotexpc_tunnel.py"})
        staging.replace(destination)
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
        "--reconnect-retries", "0",
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
            value = json.loads(response.read(64 * 1024))
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

[Service]
Type=simple
ExecStart={command}
WorkingDirectory={systemd_quote(runtime_root)}
Restart=always
RestartSec=5
Environment=PATH={systemd_quote(str(runtime_root / "bin") + ":/usr/sbin:/usr/bin")}
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

[Install]
WantedBy=multi-user.target
"""


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
    subprocess.run(["systemctl", "daemon-reload"], timeout=30, check=True)
    subprocess.run(["systemctl", "enable", "--now", UNIT_NAME], timeout=60, check=True)
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
        if arguments.action == "preflight":
            preflight(arguments.appium_home)
            print("PASS: pinned RemoteXPC runtime and /dev/net/tun are available")
            return 0
        if arguments.action == "serve":
            return serve(arguments)
        if arguments.action == "status":
            return status(arguments)
        return install_unit(arguments)
    except (TunnelError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
