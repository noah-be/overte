#!/usr/bin/env python3
"""Own a private, GPU-verified Mutter/Xwayland desktop for Linux E2E."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - constructor rejects non-Linux hosts
    fcntl = None  # type: ignore[assignment]


RUNTIME_KEY = "gpuHeadlessRuntime"
STATE_SCHEMA_VERSION = 1
HANDOFF_SCHEMA_VERSION = 1
HEX_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
DISPLAY_PATTERN = re.compile(r":[0-9]{1,5}")
MONITOR_PATTERN = re.compile(r"([1-9][0-9]{2,4})x([1-9][0-9]{2,4})")
SOFTWARE_RENDERER = re.compile(
    r"llvmpipe|softpipe|swrast|software rasterizer|swiftshader|lavapipe|"
    r"microsoft basic render driver|\bwarp\b", re.IGNORECASE)
SENTINEL = Path(__file__).resolve().with_name("gpu_headless_sentinel.py")
PROTECTED_ENVIRONMENT = {
    "AT_SPI_BUS_ADDRESS",
    "DBUS_SESSION_BUS_ADDRESS",
    "DBUS_SESSION_BUS_PID",
    "DBUS_SESSION_BUS_WINDOWID",
    "DBUS_STARTER_ADDRESS",
    "DBUS_STARTER_BUS_TYPE",
    "DESKTOP_STARTUP_ID",
    "DISPLAY",
    "GCONV_PATH",
    "GDK_BACKEND",
    "LD_AUDIT",
    "LD_DEBUG",
    "LD_LIBRARY_PATH",
    "LD_ORIGIN_PATH",
    "LD_PRELOAD",
    "LD_PROFILE",
    "MUTTER_DEBUG_DUMMY_MODE_SPECS",
    "PYTHONHOME",
    "PYTHONPATH",
    "QT_NO_XDG_DESKTOP_PORTAL",
    "QT_QPA_PLATFORM",
    "SDL_VIDEODRIVER",
    "SESSION_MANAGER",
    "WAYLAND_DISPLAY",
    "WAYLAND_SOCKET",
    "XAUTHORITY",
    "XDG_ACTIVATION_TOKEN",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
}
PROTECTED_ENVIRONMENT_PREFIXES = (
    "GALLIUM_",
    "LIBGL_",
    "MESA_",
    "MUTTER_DEBUG_",
    "VK_DRIVER_",
    "VK_ICD_",
    "__EGL_",
    "__GLX_",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expanded_path(value: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(value))).resolve()


def _process_details(
        pid: int) -> tuple[str, int, int, str, tuple[str, ...]] | None:
    """Return (start token, process group, parent, image, argv)."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return None
    try:
        raw_stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw_stat.rfind(")")
        fields = raw_stat[close + 1:].split() if close >= 0 else []
        if len(fields) <= 19 or fields[0] == "Z":
            return None
        parent = int(fields[1])
        group = int(fields[2])
        token = fields[19]
        image = os.readlink(f"/proc/{pid}/exe").removesuffix(" (deleted)")
        command = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError):
        return None
    arguments = tuple(
        item.decode("utf-8", errors="surrogateescape")
        for item in command.rstrip(b"\0").split(b"\0") if item
    )
    return token, group, parent, image, arguments


def _group_processes(group: int) -> list[tuple[int, tuple[str, int, int, str, tuple[str, ...]]]]:
    values = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        details = _process_details(pid)
        if details is not None and details[1] == group:
            values.append((pid, details))
    return values


class GpuHeadlessLifecycle:
    """Start, verify, reuse and clean one private GPU-backed desktop."""

    def __init__(self, target: dict, state_directory: Path) -> None:
        if not sys_platform_linux() or fcntl is None:
            raise RuntimeError("GPU headless desktop is supported only on Linux")
        if target.get("isolatedX11") is not True:
            raise RuntimeError("GPU headless lifecycle requires isolatedX11=true")
        self.runtime = self._validate_runtime(target.get(RUNTIME_KEY))
        self.state_directory = Path(state_directory).resolve()
        self._prepare_private_directory(self.state_directory, "GPU headless state")
        self.runtime_directory = self.state_directory / "runtime"
        self.state_path = self.state_directory / "gpu-headless.json"
        self.lock_path = self.state_directory / "gpu-headless.lock"
        self.handoff_path = self.state_directory / "display-handoff.json"
        self.log_path = self.state_directory / "mutter.log"
        self.glxinfo_path = self.state_directory / "glxinfo.txt"
        self.xrandr_path = self.state_directory / "xrandr.txt"
        socket_suffix = hashlib.sha256(
            str(self.state_directory).encode("utf-8")).hexdigest()[:16]
        self.socket_name = f"overte-e2e-{socket_suffix}"
        self.wayland_socket_path = self.runtime_directory / self.socket_name

    @staticmethod
    def _validated_executable(value: dict, path_key: str, digest_key: str) -> dict:
        raw_path = value.get(path_key)
        raw_digest = value.get(digest_key)
        if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
            raise RuntimeError(f"{path_key} must name an executable")
        if not isinstance(raw_digest, str) or not HEX_SHA256.fullmatch(raw_digest):
            raise RuntimeError(f"{digest_key} must contain 64 hexadecimal digits")
        path = _expanded_path(raw_path)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"{path_key} was not found or is not executable")
        observed = _sha256(path)
        if not secrets.compare_digest(observed.lower(), raw_digest.lower()):
            raise RuntimeError(f"{path_key} failed its SHA-256 check")
        return {"path": str(path), "sha256": observed}

    @staticmethod
    def _patterns(value: object, label: str) -> list[str]:
        if (not isinstance(value, list) or not 1 <= len(value) <= 16
                or not all(isinstance(item, str) and 1 <= len(item) <= 256
                           and "\x00" not in item for item in value)):
            raise RuntimeError(f"{label} must be a non-empty bounded regex list")
        for item in value:
            try:
                re.compile(item)
            except re.error as error:
                raise RuntimeError(f"{label} contains an invalid regex") from error
        return list(value)

    @staticmethod
    def _validate_runtime(value: object) -> dict:
        if not isinstance(value, dict):
            raise RuntimeError(f"{RUNTIME_KEY} must be an object")
        monitor = value.get("virtualMonitor", "1920x1080")
        match = MONITOR_PATTERN.fullmatch(monitor) if isinstance(monitor, str) else None
        if (not match or int(match.group(1)) > 16384
                or int(match.group(2)) > 16384):
            raise RuntimeError("GPU virtualMonitor must be bounded WIDTHxHEIGHT")
        timeout = value.get("startupTimeoutSeconds", 20.0)
        if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or not math.isfinite(float(timeout)) or not 2.0 <= float(timeout) <= 60.0):
            raise RuntimeError("GPU startup timeout must be from 2 through 60 seconds")
        result = {
            "virtualMonitor": monitor,
            "startupTimeoutSeconds": float(timeout),
        }
        for stem in ("dbusRunSession", "dbusDaemon", "mutter", "python",
                     "xwayland", "glxinfo", "xrandr"):
            result[stem] = GpuHeadlessLifecycle._validated_executable(
                value, f"{stem}Executable", f"{stem}Sha256")
        result["allowedVendorPatterns"] = GpuHeadlessLifecycle._patterns(
            value.get("allowedVendorPatterns"), "allowedVendorPatterns")
        result["allowedRendererPatterns"] = GpuHeadlessLifecycle._patterns(
            value.get("allowedRendererPatterns"), "allowedRendererPatterns")
        fingerprint_value = {**result, "sentinelSha256": _sha256(SENTINEL)}
        result["fingerprint"] = hashlib.sha256(json.dumps(
            fingerprint_value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        return result

    @staticmethod
    def _prepare_private_directory(path: Path, label: str) -> None:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        details = path.stat()
        if (not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid()
                or details.st_mode & 0o077):
            raise RuntimeError(f"{label} directory must be private and user-owned")

    @contextmanager
    def _lock(self) -> Iterator[None]:
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.lock_path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _base_environment(base: dict[str, str] | None) -> dict[str, str]:
        environment = dict(os.environ if base is None else base)
        for name in tuple(environment):
            if (name in PROTECTED_ENVIRONMENT
                    or name.startswith(PROTECTED_ENVIRONMENT_PREFIXES)):
                environment.pop(name, None)
        environment.update({
            "GIO_USE_VFS": "local",
            "GTK_USE_PORTAL": "0",
            "QT_NO_XDG_DESKTOP_PORTAL": "1",
            "NO_AT_BRIDGE": "1",
        })
        return environment

    def _compositor_environment(self, base: dict[str, str] | None) -> dict[str, str]:
        environment = self._base_environment(base)
        environment.update({
            "XDG_RUNTIME_DIR": str(self.runtime_directory),
            "XDG_SESSION_TYPE": "wayland",
        })
        return environment

    def _environment_for_state(
            self, base: dict[str, str] | None, state: dict) -> dict[str, str]:
        environment = self._base_environment(base)
        environment.update({
            "DISPLAY": state["display"],
            "XAUTHORITY": state["xauthority"],
            "XDG_RUNTIME_DIR": str(self.runtime_directory),
            "XDG_SESSION_TYPE": "x11",
            "GDK_BACKEND": "x11",
            "SDL_VIDEODRIVER": "x11",
            "QT_QPA_PLATFORM": "xcb",
        })
        # Interface and visual tools need only the owned Xwayland transport.
        for name in ("WAYLAND_DISPLAY", "WAYLAND_SOCKET", "DBUS_SESSION_BUS_ADDRESS",
                     "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE",
                     "AT_SPI_BUS_ADDRESS"):
            environment.pop(name, None)
        return environment

    def environment(self, base: dict[str, str] | None = None) -> dict[str, str]:
        state = self._read_state()
        if state is None or state.get("phase") != "ready" or not self._state_ready(state):
            raise RuntimeError("GPU headless desktop is not ready")
        return self._environment_for_state(base, state)

    def ensure_started(self, base_environment: dict[str, str] | None = None) -> dict[str, str]:
        with self._lock():
            state = self._read_state()
            if state is not None:
                if (state.get("phase") == "ready" and self._state_ready(state)
                        and state.get("runtimeFingerprint") == self.runtime["fingerprint"]):
                    return self._environment_for_state(base_environment, state)
                # Crash recovery is safe only through stored PID/token/PGID identities.
                self._cleanup_state(state)
                self._remove_artifacts(allow_owned_socket=True)
                self.state_path.unlink(missing_ok=True)
            elif self.wayland_socket_path.exists() or self.handoff_path.exists():
                raise RuntimeError("unowned GPU headless artifacts require manual inspection")

            self._prepare_private_directory(self.runtime_directory, "GPU runtime")
            for path in (self.handoff_path, self.glxinfo_path, self.xrandr_path):
                path.unlink(missing_ok=True)
            state = {
                "schemaVersion": STATE_SCHEMA_VERSION,
                "phase": "starting",
                "runtimeFingerprint": self.runtime["fingerprint"],
                "socketName": self.socket_name,
                "virtualMonitor": self.runtime["virtualMonitor"],
                "lifecycleRoot": None,
                "mutter": None,
                "sentinel": None,
                "xwayland": None,
            }
            command = [
                self.runtime["dbusRunSession"]["path"],
                f"--dbus-daemon={self.runtime['dbusDaemon']['path']}", "--",
                self.runtime["mutter"]["path"], "--headless",
                f"--virtual-monitor={self.runtime['virtualMonitor']}",
                f"--wayland-display={self.socket_name}", "--",
                self.runtime["python"]["path"], str(SENTINEL),
                "--handoff", str(self.handoff_path),
            ]
            try:
                pid = self._spawn(command, self._compositor_environment(base_environment))
                try:
                    state["lifecycleRoot"] = self._component_state(
                        pid, self.runtime["dbusRunSession"], pid, None, ())
                except BaseException:
                    self._terminate_unrecorded_child(pid, self.runtime["dbusRunSession"])
                    raise
                self._save_state(state)
                handoff = self._wait_for_handoff(state)
                state.update({
                    "display": handoff["DISPLAY"],
                    "xauthority": str(Path(handoff["XAUTHORITY"]).resolve()),
                    "mutter": self._find_one_component(
                        pid, self.runtime["mutter"], parent_pid=pid,
                        required_arguments=("--headless",
                                            f"--wayland-display={self.socket_name}")),
                })
                state["sentinel"] = self._find_one_component(
                    pid, self.runtime["python"], parent_pid=state["mutter"]["pid"],
                    required_arguments=(str(SENTINEL), str(self.handoff_path)))
                if (handoff["pid"] != state["sentinel"]["pid"]
                        or handoff["parentPid"] != state["mutter"]["pid"]
                        or handoff["processGroup"] != pid):
                    raise RuntimeError("GPU display handoff process ownership did not match")
                self._save_state(state)

                proof_environment = self._environment_for_state(base_environment, state)
                glx_output = self._run_tool(
                    self.runtime["glxinfo"], ["-B"], proof_environment, "glxinfo")
                state["xwayland"] = self._find_one_component(
                    pid, self.runtime["xwayland"], parent_pid=state["mutter"]["pid"],
                    required_arguments=(state["display"],))
                renderer = self._validate_renderer(glx_output)
                self._write_private(self.glxinfo_path, glx_output)
                xrandr_output = self._run_tool(
                    self.runtime["xrandr"], ["--current"], proof_environment, "xrandr")
                self._validate_monitor(xrandr_output)
                self._write_private(self.xrandr_path, xrandr_output)
                state["renderer"] = renderer
                state["phase"] = "ready"
                self._save_state(state)
                if not self._state_ready(state):
                    raise RuntimeError("GPU headless desktop failed final ownership checks")
                return self._environment_for_state(base_environment, state)
            except BaseException as startup_error:
                try:
                    self._cleanup_state(state)
                    self._remove_artifacts(allow_owned_socket=True)
                    self.state_path.unlink(missing_ok=True)
                except BaseException as cleanup_error:
                    raise RuntimeError(
                        "GPU headless startup and safe cleanup both failed; state was preserved"
                    ) from cleanup_error
                raise startup_error

    def _spawn(self, command: list[str], environment: dict[str, str]) -> int:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.log_path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        return os.posix_spawn(
            command[0], command, environment,
            file_actions=(
                (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                (os.POSIX_SPAWN_OPEN, 1, str(self.log_path), flags, 0o600),
                (os.POSIX_SPAWN_DUP2, 1, 2),
            ),
            setsid=True,
        )

    @staticmethod
    def _component_state(
            pid: int, executable: dict, group: int, parent_pid: int | None,
            required_arguments: tuple[str, ...]) -> dict:
        deadline = time.monotonic() + 2.0
        details = None
        while time.monotonic() < deadline:
            details = _process_details(pid)
            if details is None:
                time.sleep(0.01)
                continue
            token, observed_group, parent, image, arguments = details
            marker = executable["path"]
            if (observed_group == group
                    and (parent_pid is None or parent == parent_pid)
                    and (image == marker or marker in arguments[:4])
                    and all(item in arguments for item in required_arguments)):
                return {
                    "pid": pid,
                    "processToken": token,
                    "processGroup": observed_group,
                    "parentPid": parent,
                    "processImage": image,
                    "commandMarker": marker,
                    "executableSha256": executable["sha256"],
                    "requiredArguments": list(required_arguments),
                }
            time.sleep(0.01)
        if details is None:
            raise RuntimeError("GPU lifecycle child exited before identification")
        raise RuntimeError("GPU lifecycle child identity did not match")

    def _find_one_component(
            self, group: int, executable: dict, *, parent_pid: int,
            required_arguments: tuple[str, ...]) -> dict:
        deadline = time.monotonic() + self.runtime["startupTimeoutSeconds"]
        while time.monotonic() < deadline:
            matches = []
            marker = executable["path"]
            for pid, details in _group_processes(group):
                _, _, parent, image, arguments = details
                if (parent == parent_pid
                        and (image == marker or marker in arguments[:4])
                        and all(item in arguments for item in required_arguments)):
                    matches.append(pid)
            if len(matches) > 1:
                raise RuntimeError("GPU lifecycle component ownership is ambiguous")
            if len(matches) == 1:
                return self._component_state(
                    matches[0], executable, group, parent_pid, required_arguments)
            time.sleep(0.05)
        raise RuntimeError("GPU lifecycle component did not appear before timeout")

    def _wait_for_handoff(self, state: dict) -> dict:
        deadline = time.monotonic() + self.runtime["startupTimeoutSeconds"]
        while time.monotonic() < deadline:
            if not self._component_owned(state["lifecycleRoot"]):
                raise RuntimeError("GPU lifecycle root exited during startup")
            if self.handoff_path.exists():
                handoff = self._read_private_json(
                    self.handoff_path, "GPU display handoff")
                if handoff.get("schemaVersion") != HANDOFF_SCHEMA_VERSION:
                    raise RuntimeError("GPU display handoff schema is invalid")
                display = handoff.get("DISPLAY")
                xauthority = handoff.get("XAUTHORITY")
                wayland = handoff.get("WAYLAND_DISPLAY")
                if (not isinstance(display, str) or not DISPLAY_PATTERN.fullmatch(display)
                        or wayland != self.socket_name
                        or not isinstance(xauthority, str)):
                    raise RuntimeError("GPU display handoff values are invalid")
                auth_path = Path(xauthority).resolve()
                try:
                    auth_path.relative_to(self.runtime_directory)
                except ValueError as error:
                    raise RuntimeError("GPU Xauthority escaped the private runtime") from error
                if not self._private_file(auth_path, nonempty=True):
                    raise RuntimeError("GPU Xauthority is not private and non-empty")
                if not self._owned_socket(self.wayland_socket_path):
                    raise RuntimeError("GPU Wayland socket is not privately owned")
                for field in ("pid", "parentPid", "processGroup"):
                    if (not isinstance(handoff.get(field), int)
                            or isinstance(handoff[field], bool) or handoff[field] <= 1):
                        raise RuntimeError("GPU handoff process values are invalid")
                return handoff
            time.sleep(0.05)
        raise RuntimeError("Mutter did not publish its display handoff before timeout")

    def _run_tool(
            self, executable: dict, arguments: list[str], environment: dict[str, str],
            label: str) -> str:
        result = subprocess.run(
            [executable["path"], *arguments], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**environment, "LANG": "C", "LC_ALL": "C"},
            timeout=self.runtime["startupTimeoutSeconds"], check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"GPU {label} gate failed" + (f": {detail}" if detail else ""))
        return result.stdout

    def _validate_renderer(self, output: str) -> dict[str, str]:
        values = {}
        for line in output.splitlines():
            for label, key in (("direct rendering: ", "direct"),
                               ("OpenGL vendor string: ", "vendor"),
                               ("OpenGL renderer string: ", "renderer")):
                if line.startswith(label):
                    values[key] = line[len(label):].strip()
        if values.get("direct") != "Yes":
            raise RuntimeError("GPU headless renderer is not direct-rendered")
        combined = " ".join((values.get("vendor", ""), values.get("renderer", ""), output))
        if SOFTWARE_RENDERER.search(combined):
            raise RuntimeError("GPU headless renderer matched the software denylist")
        if not any(re.fullmatch(pattern, values.get("vendor", ""))
                   for pattern in self.runtime["allowedVendorPatterns"]):
            raise RuntimeError("GPU headless vendor is not allowlisted")
        if not any(re.fullmatch(pattern, values.get("renderer", ""))
                   for pattern in self.runtime["allowedRendererPatterns"]):
            raise RuntimeError("GPU headless renderer is not allowlisted")
        return values

    def _validate_monitor(self, output: str) -> None:
        width, height = self.runtime["virtualMonitor"].split("x")
        connected = [line for line in output.splitlines()
                     if re.match(r"^\S+ connected(?: primary)? ", line)]
        if len(connected) != 1 or not re.search(
                rf" connected(?: primary)? {re.escape(width)}x{re.escape(height)}\+", connected[0]):
            raise RuntimeError("GPU Xwayland does not expose exactly the configured monitor")
        if not re.search(
                rf"^Screen 0: .*current {re.escape(width)} x {re.escape(height)},",
                output, re.MULTILINE):
            raise RuntimeError("GPU Xwayland root extent does not match the virtual monitor")

    @staticmethod
    def _write_private(path: Path, value: str) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as output:
                output.write(value)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _private_file(path: Path, *, nonempty: bool) -> bool:
        try:
            details = path.lstat()
        except OSError:
            return False
        return (stat.S_ISREG(details.st_mode) and details.st_uid == os.getuid()
                and stat.S_IMODE(details.st_mode) == 0o600
                and (not nonempty or details.st_size > 0))

    @staticmethod
    def _owned_socket(path: Path) -> bool:
        try:
            details = path.lstat()
        except OSError:
            return False
        return stat.S_ISSOCK(details.st_mode) and details.st_uid == os.getuid()

    def _read_private_json(self, path: Path, label: str) -> dict:
        if not self._private_file(path, nonempty=True):
            raise RuntimeError(f"{label} file is not private and user-owned")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"{label} file is invalid") from error
        if not isinstance(value, dict):
            raise RuntimeError(f"{label} content is invalid")
        return value

    def _read_state(self) -> dict | None:
        if not os.path.lexists(self.state_path):
            return None
        value = self._read_private_json(self.state_path, "GPU headless state")
        if (value.get("schemaVersion") != STATE_SCHEMA_VERSION
                or value.get("phase") not in {"starting", "ready"}
                or value.get("socketName") != self.socket_name
                or value.get("virtualMonitor") != self.runtime["virtualMonitor"]):
            raise RuntimeError("GPU headless state content is invalid")
        root = value.get("lifecycleRoot")
        if root is not None and not self._component_shape_valid(root):
            raise RuntimeError("GPU lifecycle root state is invalid")
        expected_executables = {
            "lifecycleRoot": self.runtime["dbusRunSession"],
            "mutter": self.runtime["mutter"],
            "sentinel": self.runtime["python"],
            "xwayland": self.runtime["xwayland"],
        }
        for name in ("mutter", "sentinel", "xwayland"):
            component = value.get(name)
            if component is not None and not self._component_shape_valid(component):
                raise RuntimeError(f"GPU {name} state is invalid")
        for name, expected in expected_executables.items():
            component = value.get(name)
            if component is not None and (
                    component["commandMarker"] != expected["path"]
                    or not secrets.compare_digest(
                        component["executableSha256"].lower(),
                        expected["sha256"].lower())):
                raise RuntimeError(f"GPU {name} executable state is invalid")
        return value

    @staticmethod
    def _component_shape_valid(value: object) -> bool:
        return isinstance(value, dict) and (
            isinstance(value.get("pid"), int) and not isinstance(value.get("pid"), bool)
            and value["pid"] > 1
            and isinstance(value.get("processToken"), str)
            and value["processToken"].isdigit()
            and isinstance(value.get("processGroup"), int)
            and value["processGroup"] > 1
            and isinstance(value.get("parentPid"), int)
            and value["parentPid"] >= 0
            and all(isinstance(value.get(name), str) and value[name]
                    for name in ("processImage", "commandMarker", "executableSha256"))
            and bool(HEX_SHA256.fullmatch(value["executableSha256"]))
            and isinstance(value.get("requiredArguments"), list)
            and all(isinstance(item, str) for item in value["requiredArguments"])
        )

    def _save_state(self, state: dict) -> None:
        self._write_private(
            self.state_path,
            json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n")

    @staticmethod
    def _component_owned(component: dict, *, require_parent: bool = True) -> bool:
        details = _process_details(component["pid"])
        if details is None:
            return False
        token, group, parent, image, arguments = details
        return (
            token == component["processToken"]
            and group == component["processGroup"]
            and (not require_parent or parent == component["parentPid"])
            and image == component["processImage"]
            and (image == component["commandMarker"]
                 or component["commandMarker"] in arguments[:4])
            and all(item in arguments for item in component["requiredArguments"])
        )

    def _state_ready(self, state: dict) -> bool:
        display = state.get("display")
        xauthority = state.get("xauthority")
        renderer = state.get("renderer")
        if (state.get("runtimeFingerprint") != self.runtime["fingerprint"]
                or state.get("phase") != "ready"
                or not isinstance(display, str)
                or not DISPLAY_PATTERN.fullmatch(display)
                or not isinstance(xauthority, str) or not xauthority
                or "\x00" in xauthority
                or not isinstance(renderer, dict)
                or renderer.get("direct") != "Yes"
                or not all(isinstance(renderer.get(name), str) and renderer[name]
                           for name in ("vendor", "renderer"))
                or not self._owned_socket(self.wayland_socket_path)
                or not self._private_file(self.handoff_path, nonempty=True)
                or not self._private_file(self.glxinfo_path, nonempty=True)
                or not self._private_file(self.xrandr_path, nonempty=True)):
            return False
        try:
            auth_path = Path(xauthority).resolve()
            auth_path.relative_to(self.runtime_directory)
        except (OSError, RuntimeError, ValueError):
            return False
        if str(auth_path) != xauthority or not self._private_file(auth_path, nonempty=True):
            return False
        try:
            proof_renderer = self._validate_renderer(
                self.glxinfo_path.read_text(encoding="utf-8"))
            self._validate_monitor(self.xrandr_path.read_text(encoding="utf-8"))
        except (OSError, RuntimeError):
            return False
        if proof_renderer != renderer:
            return False
        components = [state.get(name) for name in (
            "lifecycleRoot", "mutter", "sentinel", "xwayland")]
        if any(component is None or not self._component_owned(component)
               for component in components):
            return False
        root = state["lifecycleRoot"]
        if root["processGroup"] != root["pid"]:
            return False
        if not all(component["processGroup"] == root["pid"] for component in components[1:]):
            return False
        try:
            handoff = self._read_private_json(
                self.handoff_path, "GPU display handoff")
            handoff_auth = Path(handoff.get("XAUTHORITY", "")).resolve()
        except (OSError, RuntimeError, TypeError, ValueError):
            return False
        return (
            handoff.get("schemaVersion") == HANDOFF_SCHEMA_VERSION
            and handoff.get("DISPLAY") == display
            and handoff.get("WAYLAND_DISPLAY") == self.socket_name
            and handoff_auth == auth_path
            and handoff.get("pid") == state["sentinel"]["pid"]
            and handoff.get("parentPid") == state["mutter"]["pid"]
            and handoff.get("processGroup") == root["pid"]
        )

    @staticmethod
    def _group_exists(group: int) -> bool:
        try:
            os.killpg(group, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def _reap_if_child(pid: int) -> None:
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass

    @staticmethod
    def _terminate_unrecorded_child(pid: int, executable: dict) -> None:
        details = _process_details(pid)
        if details is None:
            return
        token, group, _, image, arguments = details
        marker = executable["path"]
        if group != pid or (image != marker and marker not in arguments[:4]):
            return
        snapshot = {member_pid: member_details[0]
                    for member_pid, member_details in _group_processes(group)}
        if snapshot.get(pid) != token:
            return
        try:
            os.killpg(group, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 5.0
        while _group_processes(group) and time.monotonic() < deadline:
            GpuHeadlessLifecycle._reap_if_child(pid)
            time.sleep(0.05)
        remaining = _group_processes(group)
        if remaining:
            if any(snapshot.get(member_pid) != member_details[0]
                   for member_pid, member_details in remaining):
                raise RuntimeError(
                    "refusing to force a reused unrecorded GPU process group")
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 5.0
            while _group_processes(group) and time.monotonic() < deadline:
                GpuHeadlessLifecycle._reap_if_child(pid)
                time.sleep(0.05)
        GpuHeadlessLifecycle._reap_if_child(pid)
        if _group_processes(group):
            raise RuntimeError("unrecorded GPU process group could not be terminated")

    def cleanup(self) -> bool:
        with self._lock():
            state = self._read_state()
            if state is None:
                if self.wayland_socket_path.exists() or self.handoff_path.exists():
                    raise RuntimeError("refusing to remove unowned GPU headless artifacts")
                self._remove_artifacts(allow_owned_socket=False)
                return False
            self._cleanup_state(state)
            self._remove_artifacts(allow_owned_socket=True)
            self.state_path.unlink(missing_ok=True)
            return True

    def _cleanup_state(self, state: dict) -> None:
        root = state.get("lifecycleRoot")
        if root is None:
            return
        group = root["processGroup"]
        if not self._group_exists(group):
            self._reap_if_child(root["pid"])
            return
        recorded = [state.get(name) for name in (
            "lifecycleRoot", "mutter", "sentinel", "xwayland")]
        live_recorded = [component for component in recorded
                         if component is not None and _process_details(component["pid"]) is not None]
        if not live_recorded:
            # killpg(0) can still see unreaped zombies although /proc contains
            # no signalable member. Fail closed if the PGID has instead been
            # reused by any unrecorded live process.
            if _group_processes(group):
                raise RuntimeError(
                    "refusing to recover a reused GPU process group")
            self._reap_if_child(root["pid"])
            return
        # Children can be reparented after a compositor crash. Their immutable
        # start token, PGID, executable and required argv still bind them to
        # this lifecycle; requiring the now-stale PPID would prevent recovery.
        if any(not self._component_owned(component, require_parent=False)
               for component in live_recorded):
            raise RuntimeError("refusing to signal GPU process group with mismatched identity")
        snapshot = {pid: details[0] for pid, details in _group_processes(group)}
        if not any(snapshot.get(component["pid"]) == component["processToken"]
                   for component in live_recorded):
            if snapshot:
                raise RuntimeError(
                    "refusing to signal GPU process group after losing its ownership anchor")
            self._reap_if_child(root["pid"])
            return
        os.killpg(group, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while _group_processes(group) and time.monotonic() < deadline:
            self._reap_if_child(root["pid"])
            time.sleep(0.05)
        remaining = _group_processes(group)
        if remaining:
            if any(snapshot.get(pid) != details[0] for pid, details in remaining):
                raise RuntimeError(
                    "refusing to force a reused GPU process group")
            os.killpg(group, signal.SIGKILL)
            deadline = time.monotonic() + 5.0
            while _group_processes(group) and time.monotonic() < deadline:
                self._reap_if_child(root["pid"])
                time.sleep(0.05)
        self._reap_if_child(root["pid"])
        if _group_processes(group):
            raise RuntimeError("owned GPU process group could not be terminated")

    def _remove_artifacts(self, *, allow_owned_socket: bool) -> None:
        if os.path.lexists(self.wayland_socket_path):
            if not allow_owned_socket or not self._owned_socket(self.wayland_socket_path):
                raise RuntimeError("refusing to remove an unowned GPU Wayland endpoint")
            # The recorded process group was proven absent immediately before
            # this call. An exact socket left by a crash inside the private
            # runtime can therefore be recovered safely.
            self.wayland_socket_path.unlink()
        for path in (self.handoff_path, self.glxinfo_path, self.xrandr_path):
            path.unlink(missing_ok=True)
        if self.runtime_directory.exists():
            resolved = self.runtime_directory.resolve()
            if resolved.parent != self.state_directory:
                raise RuntimeError("refusing to remove unexpected GPU runtime path")
            shutil.rmtree(resolved)


def sys_platform_linux() -> bool:
    import sys
    return sys.platform.startswith("linux")


def ensure_gpu_headless(
        target: dict, state_directory: Path,
        base_environment: dict[str, str] | None = None) -> dict[str, str]:
    return GpuHeadlessLifecycle(target, state_directory).ensure_started(base_environment)


def cleanup_gpu_headless(target: dict, state_directory: Path) -> bool:
    return GpuHeadlessLifecycle(target, state_directory).cleanup()
