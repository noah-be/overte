#!/usr/bin/env python3
"""Linux desktop adapter with target-scoped Wayland and private X11 input."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEVICE_ROOT = Path(__file__).resolve().parents[2]
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))

from adapters.common import (emit, fail, parse_operation_arguments,  # noqa: E402
                             read_fresh_json, state_directory)
from adapters.linux.gpu_headless import GpuHeadlessLifecycle  # noqa: E402
from adapters.linux.wayland_libei_client import (  # noqa: E402
    WaylandInputClient,
    WaylandInputError,
    default_socket_path,
)
from contracts import validate_operation_arguments  # noqa: E402


PROBE_SCRIPT = DEVICE_ROOT / "probe" / "overte_e2e_probe.js"


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("discover", "describe", "invoke", "cleanup", "authorize-input"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    return parser.parse_args()


def expanded_path(value: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(value))).resolve()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class LinuxAdapter:
    def __init__(self) -> None:
        self.adapter_id = "linux-desktop"
        self.targets = self.load_targets()
    def require_interactive_host(self) -> None:
        physical_targets = [
            target for target in self.targets.values()
            if target.get("physical") is True and target.get("enabled", True)
        ]
        if physical_targets and not sys.platform.startswith("linux"):
            fail("physical Linux desktop targets require a Linux host")
        interactive_targets = [
            target for target in physical_targets if not target.get("isolatedX11")
        ]
        if interactive_targets:
            session = os.environ.get("XDG_SESSION_TYPE", "").lower()
            xwayland = (session == "wayland" and all(
                target.get("xwayland") is True
                and target.get("environment", {}).get("QT_QPA_PLATFORM") == "xcb"
                for target in interactive_targets
            ))
            if session != "x11" and not xwayland:
                fail("visible Linux targets require X11 or explicit xcb/XWayland")
            if not os.environ.get("DISPLAY"):
                fail("visible Linux targets require DISPLAY")
        for target in physical_targets:
            if target.get("inputDriver") == "wayland-libei":
                self.linux_tool(
                    target, "waylandInputDaemonExecutable",
                    "waylandInputDaemonSha256", "Wayland/libei daemon")
    def load_targets(self) -> dict[str, dict]:
        config_value = os.environ.get("OVERTE_LINUX_TARGETS")
        if not config_value:
            fail("OVERTE_LINUX_TARGETS must name a private target configuration")
        payload = json.loads(expanded_path(config_value).read_text(encoding="utf-8"))
        entries = payload.get("targets")
        if payload.get("schemaVersion") != 1 or not isinstance(entries, list):
            fail("unsupported desktop target configuration schema")
        targets: dict[str, dict] = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("platform") != "linux":
                fail("desktop target configuration contains an invalid target")
            selector = entry.get("selector")
            if not isinstance(selector, str) or not selector or selector in targets:
                fail("desktop target selectors must be unique non-empty strings")
            if not all(isinstance(entry.get(field), str) and entry[field]
                       for field in ("executable", "windowTitle")):
                fail("desktop target requires executable and windowTitle")
            if not isinstance(entry.get("arguments", []), list) or not all(
                    isinstance(item, str) for item in entry.get("arguments", [])):
                fail("desktop target arguments must be a string list")
            environment = entry.get("environment", {})
            if (not isinstance(environment, dict) or not all(
                    isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
                    and isinstance(value, str) and "\x00" not in value
                    for key, value in environment.items())):
                fail("desktop target environment must contain safe string assignments")
            probe = entry.get("probe")
            if probe is not None:
                if not isinstance(probe, dict) or probe.get("kind") not in {
                        "host-file", "injected-test-script"}:
                    fail("desktop probe must use a supported transport")
                if (probe["kind"] == "host-file"
                        and (not isinstance(probe.get("path"), str)
                             or not probe["path"] or "\x00" in probe["path"])):
                    fail("desktop host-file probe requires a safe path")
            control = entry.get("clientControl")
            if control is not None:
                if (not isinstance(control, dict)
                        or control != {"kind": "fixture-command-http"}):
                    fail("desktop clientControl must select only fixture-command-http")
                if not isinstance(probe, dict) or probe.get("kind") != "injected-test-script":
                    fail("desktop clientControl requires the injected in-client probe")
            if not isinstance(entry.get("xwayland", False), bool):
                fail("desktop target xwayland must be boolean")
            if not isinstance(entry.get("isolatedX11", False), bool):
                fail("desktop target isolatedX11 must be boolean")
            if (entry.get("xwayland")
                    and environment.get("QT_QPA_PLATFORM") != "xcb"):
                fail("xwayland requires a Linux target with QT_QPA_PLATFORM=xcb")
            if entry.get("isolatedX11"):
                if (entry.get("xwayland")
                        or environment.get("QT_QPA_PLATFORM") != "xcb"
                        or "DISPLAY" in environment or "XAUTHORITY" in environment
                        or not isinstance(entry.get("gpuHeadlessRuntime"), dict)):
                    fail("isolatedX11 requires Linux, xcb and a GPU headless runtime")
                # Disabled example/lab slots may be intentionally unprovisioned.
                # Validate every executable and digest before an enabled target
                # can be discovered or start a process.
                if entry.get("enabled", True):
                    GpuHeadlessLifecycle._validate_runtime(entry["gpuHeadlessRuntime"])
            if entry["platform"] == "linux":
                expected_driver = "xdotool" if entry.get("isolatedX11") else "wayland-libei"
                if entry.get("inputDriver") != expected_driver:
                    fail(f"Linux target inputDriver must be {expected_driver}")
                if expected_driver == "xdotool":
                    if (not isinstance(entry.get("xdotoolExecutable"), str)
                            or not re.fullmatch(
                                r"[0-9a-fA-F]{64}", entry.get("xdotoolSha256", ""))):
                        fail("GPU headless Xwayland requires a pinned xdotool executable")
                    if (not isinstance(entry.get("screenshotExecutable"), str)
                            or not re.fullmatch(
                                r"[0-9a-fA-F]{64}", entry.get("screenshotSha256", ""))):
                        fail("GPU headless Xwayland requires a pinned screenshot executable")
                    if (not isinstance(entry.get("screenshotArguments", []), list)
                            or not all(isinstance(item, str) and "\x00" not in item
                                       for item in entry.get("screenshotArguments", []))):
                        fail("Linux screenshotArguments must be a NUL-free string list")
                else:
                    if (not isinstance(entry.get("waylandInputTarget"), str)
                            or not re.fullmatch(
                                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}",
                                entry.get("waylandInputTarget", ""))):
                        fail("visible Wayland requires a safe waylandInputTarget")
                    if (not isinstance(entry.get("waylandInputDaemonExecutable"), str)
                            or not re.fullmatch(
                                r"[0-9a-fA-F]{64}",
                                entry.get("waylandInputDaemonSha256", ""))):
                        fail("visible Wayland requires a pinned libei daemon")
                    size = entry.get("desktopSize")
                    if (not isinstance(size, dict)
                            or any(not isinstance(size.get(axis), int)
                                   or isinstance(size.get(axis), bool)
                                   or not 320 <= size[axis] <= 16384
                                   for axis in ("width", "height"))):
                        fail("visible Wayland requires a bounded desktopSize")
                    for root_field in ("waylandInputStateRoot", "waylandInputRuntimeRoot"):
                        root_value = entry.get(root_field)
                        if (root_value is not None and (not isinstance(root_value, str)
                                or not root_value or "\x00" in root_value
                                or not expanded_path(root_value).is_absolute())):
                            fail(f"{root_field} must be an absolute NUL-free path")
                    portal_timeout = entry.get("waylandInputPortalTimeoutSeconds", 300)
                    if (not isinstance(portal_timeout, int)
                            or isinstance(portal_timeout, bool)
                            or not 10 <= portal_timeout <= 1800):
                        fail("waylandInputPortalTimeoutSeconds must be from 10 through 1800")
            targets[selector] = entry
        return targets

    @staticmethod
    def capabilities(target: dict) -> list[str]:
        controlled = LinuxAdapter.controlled_client(target)
        keyboard_input = not target.get("isolatedX11") or controlled
        values = ["app.foreground", "app.launch", "app.process", "app.stop",
                  "input.look"]
        if keyboard_input:
            values += ["input.fly", "input.jump", "input.move"]
        if target.get("isolatedX11"):
            values.append("artifact.screenshot")
        if target.get("probe"):
            values.append("probe.snapshot")
            if keyboard_input:
                values += ["tablet.close", "tablet.open"]
        if controlled:
            values += ["asset.load", "navigation.enter-domain", "scene.load",
                       "sound.play"]
        return sorted(values)

    @staticmethod
    def controlled_client(target: dict) -> bool:
        probe = target.get("probe")
        return (isinstance(probe, dict)
                and probe.get("kind") == "injected-test-script"
                and target.get("clientControl") == {"kind": "fixture-command-http"})

    def discover(self) -> list[dict]:
        self.require_interactive_host()
        return [{
            "selector": selector,
            "displayName": target.get("displayName", "Overte Linux"),
            "platform": "linux",
            "physical": target.get("physical") is True,
            "capabilities": self.capabilities(target),
        } for selector, target in sorted(self.targets.items()) if target.get("enabled", True)]

    def target(self, selector: str) -> dict:
        target = self.targets.get(selector)
        if not target or not target.get("enabled", True):
            fail("requested desktop target is not configured")
        return target

    def target_environment(self, target: dict, *, visual_driver: bool = False) -> dict[str, str]:
        """Build a target environment without leaking Wayland portal access."""
        environment = os.environ.copy()
        environment.pop("HIFI_ALLOW_MULTIPLE_INSTANCES", None)
        environment.update(target.get("environment", {}))
        if target.get("isolatedX11"):
            for name in ("WAYLAND_DISPLAY", "WAYLAND_SOCKET", "MUTTER_DEBUG_DUMMY_MODE_SPECS"):
                environment.pop(name, None)
            environment.update({
                "XDG_SESSION_TYPE": "x11",
                "GDK_BACKEND": "x11",
                "SDL_VIDEODRIVER": "x11",
                "QT_QPA_PLATFORM": "xcb",
                "GTK_USE_PORTAL": "0",
                "QT_NO_XDG_DESKTOP_PORTAL": "1",
            })
            if visual_driver:
                # Capture and input helpers need X11 only. With no session bus
                # address they cannot invoke GNOME desktop portals.
                environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        return environment

    def selector_for_target(self, target: dict) -> str:
        for selector, candidate in self.targets.items():
            if candidate is target:
                return selector
        fail("desktop target identity is not configured")

    def gpu_headless_lifecycle(self, target: dict) -> GpuHeadlessLifecycle:
        selector = self.selector_for_target(target)
        return GpuHeadlessLifecycle(
            target, state_directory(self.adapter_id, selector) / "gpu-headless")

    def runtime_environment(self, target: dict, *, visual_driver: bool = False,
                            start_isolated: bool = False) -> dict[str, str]:
        environment = self.target_environment(target, visual_driver=visual_driver)
        if target.get("isolatedX11"):
            lifecycle = self.gpu_headless_lifecycle(target)
            return (lifecycle.ensure_started(environment) if start_isolated
                    else lifecycle.environment(environment))
        return environment

    def describe(self, selector: str) -> dict:
        target = self.target(selector)
        return {
            "adapter": self.adapter_id,
            "model": target.get("model", "physical desktop"),
            "os": "linux",
            "osVersion": target.get("osVersion"),
            "role": "physical-desktop-e2e",
        }

    def state_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "process.json"

    def wayland_input_state_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "wayland-input.json"

    def wayland_input_socket_path(self, target: dict) -> Path:
        runtime_root = target.get("waylandInputRuntimeRoot")
        return default_socket_path(
            target["waylandInputTarget"],
            expanded_path(runtime_root) if runtime_root else None,
        )

    def read_wayland_input_state(self, selector: str) -> dict | None:
        path = self.wayland_input_state_path(selector)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) and isinstance(value.get("pid"), int) else None

    def save_wayland_input_state(self, selector: str, state: dict) -> None:
        path = self.wayland_input_state_path(selector)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)

    def wayland_input_client(self, target: dict) -> WaylandInputClient:
        return WaylandInputClient(self.wayland_input_socket_path(target))

    def ensure_wayland_input(self, selector: str, target: dict, *, authorize: bool) -> dict:
        if target.get("inputDriver") != "wayland-libei":
            fail("input authorization is only available for visible Linux Wayland targets")
        self.require_interactive_host()
        existing = self.read_wayland_input_state(selector)
        if existing and self.state_alive(existing):
            expected_identity = {
                "executable": str(expanded_path(target["waylandInputDaemonExecutable"])),
                "executableSha256": target["waylandInputDaemonSha256"].lower(),
                "socket": str(self.wayland_input_socket_path(target)),
            }
            if any(existing.get(field) != value
                   for field, value in expected_identity.items()):
                fail("owned Wayland input daemon does not match the configured target")
            try:
                status = self.wayland_input_client(target).status()
            except WaylandInputError as error:
                fail(f"owned Wayland input daemon is unhealthy: {error}")
            if not all(status.values()):
                fail("owned Wayland input daemon has incomplete input capabilities")
            return {"ready": True, "authorized": authorize, "reused": True}
        if existing:
            self.wayland_input_state_path(selector).unlink(missing_ok=True)

        daemon = self.linux_tool(
            target, "waylandInputDaemonExecutable", "waylandInputDaemonSha256",
            "Wayland/libei daemon")
        arguments = [str(daemon), "--target", target["waylandInputTarget"]]
        state_root = target.get("waylandInputStateRoot")
        runtime_root = target.get("waylandInputRuntimeRoot")
        if state_root:
            arguments += ["--state-root", str(expanded_path(state_root))]
        if runtime_root:
            arguments += ["--runtime-root", str(expanded_path(runtime_root))]
        portal_timeout = int(target.get("waylandInputPortalTimeoutSeconds", 300))
        arguments += ["--portal-timeout", str(portal_timeout)]
        if authorize:
            arguments.append("--authorize")

        log = state_directory(self.adapter_id, selector) / "wayland-input.log"
        log.unlink(missing_ok=True)
        with log.open("ab") as output:
            process = subprocess.Popen(
                arguments, stdout=output, stderr=subprocess.STDOUT,
                env=os.environ.copy(), start_new_session=True,
            )
        token = self.process_token(process.pid)
        if token is None:
            process.terminate()
            fail("launched Wayland input daemon could not be identified")
        state = {
            "pid": process.pid,
            "processToken": token,
            "identity": f"{process.pid}:{token}",
            "executable": str(daemon),
            "executableSha256": target["waylandInputDaemonSha256"].lower(),
            "socket": str(self.wayland_input_socket_path(target)),
        }
        self.save_wayland_input_state(selector, state)
        deadline = time.monotonic() + (portal_timeout + 10 if authorize else 45)
        expected = f"READY socket={state['socket']}"
        try:
            while time.monotonic() < deadline:
                if not self.state_alive(state):
                    detail = log.read_text(encoding="utf-8", errors="replace")[-2000:].strip()
                    fail("Wayland input daemon exited before readiness"
                         + (f": {detail}" if detail else ""))
                output = log.read_text(encoding="utf-8", errors="replace")
                if expected in output.splitlines():
                    status = self.wayland_input_client(target).status()
                    if not all(status.values()):
                        fail("Wayland input daemon has incomplete input capabilities")
                    return {"ready": True, "authorized": authorize, "reused": False}
                time.sleep(0.1)
            fail("Wayland input daemon did not become ready before its bounded timeout")
        except (OSError, RuntimeError, WaylandInputError):
            self.stop_wayland_input(selector, target)
            raise

    def stop_wayland_input(self, selector: str, target: dict) -> None:
        state = self.read_wayland_input_state(selector)
        if state and self.state_alive(state):
            try:
                endpoint = state.get("socket")
                if not isinstance(endpoint, str) or not os.path.isabs(endpoint):
                    raise WaylandInputError("owned daemon state has no absolute socket")
                WaylandInputClient(endpoint).shutdown()
            except WaylandInputError:
                pass
            deadline = time.monotonic() + 5
            while self.state_alive(state) and time.monotonic() < deadline:
                time.sleep(0.05)
        if state and self.process_tree_alive(state):
            try:
                self.terminate_process_tree(state["pid"], force=False)
            except OSError:
                pass
            deadline = time.monotonic() + 3
            while self.process_tree_alive(state) and time.monotonic() < deadline:
                time.sleep(0.05)
            if self.process_tree_alive(state):
                try:
                    self.terminate_process_tree(state["pid"], force=True)
                except OSError:
                    pass
        self.wayland_input_state_path(selector).unlink(missing_ok=True)

    def read_state(self, selector: str) -> dict | None:
        path = self.state_path(selector)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) and isinstance(value.get("pid"), int) else None

    @staticmethod
    def process_token(pid: int) -> str | None:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except OSError:
            return None
        close = stat.rfind(")")
        fields = stat[close + 1:].split() if close >= 0 else []
        if len(fields) <= 19 or fields[0] == "Z" or not fields[19].isdigit():
            return None
        return fields[19]

    @classmethod
    def alive(cls, pid: int, expected_token: str | None = None) -> bool:
        observed = cls.process_token(pid)
        return observed is not None and (expected_token is None or observed == expected_token)

    @classmethod
    def state_alive(cls, state: dict) -> bool:
        token = state.get("processToken")
        return isinstance(token, str) and bool(token) and cls.alive(state["pid"], token)

    @classmethod
    def process_tree_alive(cls, state: dict) -> bool:
        """Return whether the launched Linux process group still needs cleanup."""
        process_group = state["pid"]
        for stat_path in Path("/proc").glob("[0-9]*/stat"):
            try:
                stat = stat_path.read_text(encoding="utf-8")
            except OSError:
                continue
            close = stat.rfind(")")
            fields = stat[close + 1:].split() if close >= 0 else []
            if (len(fields) > 2 and fields[0] != "Z"
                    and fields[2].isdigit() and int(fields[2]) == process_group):
                return True
        return False

    @staticmethod
    def terminate_process_tree(pid: int, *, force: bool) -> None:
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)

    def probe_path(self, selector: str, target: dict) -> Path:
        probe = target.get("probe", {})
        if probe.get("kind") == "host-file":
            path = probe.get("path")
            if not isinstance(path, str):
                fail("desktop host-file probe requires a path")
            return expanded_path(path)
        if probe.get("kind") == "injected-test-script":
            return state_directory(self.adapter_id, selector) / "probe" / "overte-probe.json"
        fail("unsupported desktop probe transport")

    def probe_script_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "probe" / PROBE_SCRIPT.name

    def prepare_injected_probe(self, selector: str) -> Path:
        result_dir = self.probe_script_path(selector).parent
        result_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        script = self.probe_script_path(selector)
        temporary = script.with_suffix(script.suffix + ".tmp")
        shutil.copyfile(PROBE_SCRIPT, temporary)
        temporary.chmod(0o600)
        temporary.replace(script)
        return script

    def client_command_endpoint(self, scene_url: str) -> str:
        self.controlled_http_url(scene_url, "controlled scene URL")
        parsed = urlsplit(scene_url)
        return urlunsplit((parsed.scheme, parsed.netloc,
                           "/e2e-client-command.json", "", ""))

    def post_client_command(self, scene_url: str, command: dict) -> None:
        payload = json.dumps(command, separators=(",", ":")).encode("utf-8")
        if len(payload) > 4096:
            fail("desktop client command exceeds the fixture limit")
        request = Request(
            self.client_command_endpoint(scene_url), data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                fail("controlled fixture rejected the desktop client command")
            encoded = response.read(4097)
        if len(encoded) > 4096:
            fail("controlled fixture returned an oversized client command response")
        try:
            accepted = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "controlled fixture returned an invalid client command response") from error
        if accepted != command:
            fail("controlled fixture did not acknowledge the exact desktop client command")

    def write_client_command(
            self, selector: str, target: dict, state: dict, command: dict) -> None:
        if not self.controlled_client(target):
            fail("desktop operation requires the controlled in-client probe channel")
        if not self.state_alive(state):
            fail("Overte desktop process changed before the in-client command")
        scene_url = state.get("initialSceneUrl")
        if not isinstance(scene_url, str):
            fail("desktop in-client command channel requires the controlled scene origin")
        self.post_client_command(scene_url, command)
        if not self.state_alive(state):
            fail("Overte desktop process changed while delivering the in-client command")

    def controlled_key_hold(
            self, selector: str, target: dict, state: dict,
            key: str, duration_seconds: float) -> None:
        if not target.get("isolatedX11"):
            fail("controlled key holds are restricted to private headless X11")
        duration_ms = round(float(duration_seconds) * 1000.0)
        if not 50 <= duration_ms <= 10000:
            fail("controlled key hold duration must be from 50 through 10000 ms")
        self.write_client_command(selector, target, state, {
            "schemaVersion": 1,
            "commandId": "key-" + uuid.uuid4().hex,
            "action": "key-hold",
            "key": key,
            "durationMs": duration_ms,
        })

    def probe_snapshot(
            self, selector: str, target: dict, state: dict,
            after_sample_sequence: int | None) -> dict:
        deadline = time.monotonic() + 5.0
        while True:
            if not self.state_alive(state):
                fail("Overte desktop process changed while reading the probe snapshot")
            snapshot = read_fresh_json(self.probe_path(selector, target))
            sequence = snapshot.get("sampleSequence")
            if after_sample_sequence is None or (
                    isinstance(sequence, int) and not isinstance(sequence, bool)
                    and sequence > after_sample_sequence):
                return snapshot
            if time.monotonic() >= deadline:
                fail("probe snapshot sampleSequence did not advance")
            time.sleep(0.05)

    @staticmethod
    def signed_angle_delta(first: float, second: float) -> float:
        return (float(second) - float(first) + 180.0) % 360.0 - 180.0

    def controlled_look(
            self, selector: str, target: dict, state: dict, values: dict) -> None:
        if not target.get("probe") or not target.get("isolatedX11"):
            self.visual_action(target, "look", {**values, "processId": state["pid"]})
            return
        before = read_fresh_json(self.probe_path(selector, target))
        orientation = before.get("view", {}).get("orientation", {})
        horizontal = float(values.get("horizontal", 0.25))
        vertical = float(values.get("vertical", 0.0))
        axis = "y" if abs(horizontal) >= abs(vertical) else "x"
        requested = horizontal if axis == "y" else vertical
        requested_sign = 1.0 if requested > 0.0 else -1.0
        baseline = orientation.get(axis)
        sequence = before.get("sampleSequence")
        if (not isinstance(baseline, (int, float)) or isinstance(baseline, bool)
                or not isinstance(sequence, int) or isinstance(sequence, bool)):
            fail("desktop probe has no usable look orientation")
        for _attempt in range(3):
            self.visual_action(target, "look", {**values, "processId": state["pid"]})
            for _sample in range(10):
                current = read_fresh_json(self.probe_path(selector, target))
                current_sequence = current.get("sampleSequence")
                current_axis = current.get("view", {}).get("orientation", {}).get(axis)
                if (isinstance(current_sequence, int) and not isinstance(
                        current_sequence, bool) and current_sequence > sequence
                        and isinstance(current_axis, (int, float))
                        and not isinstance(current_axis, bool)
                        and requested_sign * self.signed_angle_delta(
                            float(baseline), float(current_axis)) >= 1.0):
                    return
                time.sleep(0.1)
        fail("desktop look input did not produce the requested camera rotation")

    def settle_controlled_scene(
            self, selector: str, target: dict, state: dict,
            observe_after_monotonic: float = 0.0) -> None:
        deadline = time.monotonic() + 30.0
        requested_grounding = False
        while time.monotonic() < deadline:
            if not self.state_alive(state):
                fail("Overte desktop process changed while grounding the controlled scene")
            try:
                snapshot = read_fresh_json(self.probe_path(selector, target))
                scene = snapshot["scene"]
                avatar = snapshot["avatar"]
            except (KeyError, TypeError, RuntimeError):
                time.sleep(0.1)
                continue
            if scene.get("ready") is True and scene.get("spawnValidated") is True:
                # The shared probe deliberately reapplies a fixture viewpoint
                # at 1.5 and 3.5 seconds. Do not accept or alter the avatar
                # until those bounded reload timers have completed.
                if time.monotonic() < observe_after_monotonic:
                    time.sleep(0.1)
                    continue
                if avatar.get("inAir") is False and avatar.get("flying") is False:
                    return
                if not requested_grounding:
                    self.visual_action(target, "settle", {"processId": state["pid"]})
                    requested_grounding = True
            time.sleep(0.1)
        fail("controlled desktop scene did not reach a grounded spawn")

    @staticmethod
    def controlled_http_url(value: str, label: str) -> tuple[str, str, int | None]:
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as error:
            fail(f"{label} has an invalid port")
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment):
            fail(f"{label} must be an absolute credential-free HTTP(S) URL")
        return parsed.scheme, parsed.hostname.lower(), port

    def request_sound(self, selector: str, target: dict,
                      state: dict, values: dict) -> dict:
        sound_origin = self.controlled_http_url(values["url"], "sound.play url")
        command_origin = self.controlled_http_url(
            values["commandUrl"], "sound.play commandUrl")
        command_url = urlsplit(values["commandUrl"])
        if (sound_origin != command_origin or command_url.path != "/sound-command.json"
                or command_url.query):
            fail("sound.play URLs must use the same controlled fixture origin and command path")
        payload = {
            "schemaVersion": 1,
            "commandId": values["commandId"],
            "action": "play",
            "soundUrl": values["url"],
        }
        request = Request(
            values["commandUrl"],
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                fail("controlled fixture rejected the sound command")
            encoded = response.read(4097)
        if len(encoded) > 4096:
            fail("controlled fixture returned an oversized sound response")
        try:
            accepted = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("controlled fixture returned an invalid sound response") from error
        if accepted != payload:
            fail("controlled fixture did not acknowledge the exact sound command")
        self.write_client_command(selector, target, state, {
            "schemaVersion": 1,
            "commandId": "sound-channel-" + values["commandId"],
            "action": "sound-channel",
            "url": values["commandUrl"],
        })
        return {"requested": True, "commandId": values["commandId"]}

    def save_state(self, selector: str, state: dict) -> None:
        path = self.state_path(selector)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def launch(self, selector: str, target: dict) -> dict:
        state = self.read_state(selector)
        if state and self.state_alive(state):
            self.visual_action(target, "focus", {"processId": state["pid"]})
            return {"launched": True}
        self.require_interactive_host()
        if target.get("inputDriver") == "wayland-libei":
            self.ensure_wayland_input(selector, target, authorize=False)
        executable = expanded_path(target["executable"])
        if not executable.is_file():
            fail("configured Overte desktop executable was not found")
        configured_arguments = target.get("arguments", [])
        controlled = {"--allowMultipleInstances", "--display", "--testScript",
                      "--testResultsLocation", "--url"}
        if any(item in controlled or any(item.startswith(option + "=") for option in controlled)
               for item in configured_arguments):
            fail("desktop target arguments contain a harness-controlled option")
        arguments = [str(executable), *configured_arguments,
                     "--no-launcher", "--no-updater", "--no-login-suggestion",
                     "--display=Desktop"]
        initial_scene_url = os.environ.get("OVERTE_E2E_SCENE_URL")
        if initial_scene_url:
            if "://" not in initial_scene_url or "\x00" in initial_scene_url:
                fail("OVERTE_E2E_SCENE_URL must be an absolute URL")
            # Loading the fixture as part of the one authoritative process is
            # intentional. Starting Interface again merely to forward --url
            # can race its local socket, display a second mode selector, and
            # makes process lifecycle assertions ambiguous.
            arguments += ["--url", initial_scene_url]
        if self.controlled_client(target):
            if not initial_scene_url:
                fail("controlled desktop target requires OVERTE_E2E_SCENE_URL")
            self.post_client_command(initial_scene_url, {
                "schemaVersion": 1, "commandId": "", "action": "idle",
            })
        probe = target.get("probe", {})
        if probe.get("kind") == "injected-test-script":
            result_dir = self.probe_path(selector, target).parent
            result_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.probe_path(selector, target).unlink(missing_ok=True)
            script = self.prepare_injected_probe(selector)
            arguments += ["--testScript", str(script),
                          "--testResultsLocation", str(result_dir)]
        working = expanded_path(target.get("workingDirectory", str(executable.parent)))
        if not working.is_dir():
            fail("configured desktop working directory was not found")
        log = state_directory(self.adapter_id, selector) / "interface.log"
        with log.open("ab") as output:
            isolated_lifecycle = None
            if target.get("isolatedX11"):
                isolated_lifecycle = self.gpu_headless_lifecycle(target)
                environment = isolated_lifecycle.ensure_started(
                    self.target_environment(target))
            else:
                environment = self.runtime_environment(target)
            options: dict = {
                "cwd": working,
                "stdout": output,
                "stderr": subprocess.STDOUT,
                "env": environment,
                "start_new_session": True,
            }
            try:
                process = subprocess.Popen(arguments, **options)
            except BaseException:
                if isolated_lifecycle is not None:
                    isolated_lifecycle.cleanup()
                raise
        token = self.process_token(process.pid)
        if token is None:
            process.terminate()
            fail("launched Overte process could not be identified")
        state = {"pid": process.pid, "processToken": token,
                 "identity": f"{process.pid}:{token}",
                 "initialSceneUrl": initial_scene_url}
        self.save_state(selector, state)
        try:
            self.visual_action(target, "focus", {"processId": process.pid})
        except RuntimeError:
            self.cleanup(selector)
            raise
        return {"launched": True}

    def linux_tool(self, target: dict, path_field: str, hash_field: str,
                   description: str) -> Path:
        executable = expanded_path(target[path_field])
        if (not executable.is_file() or not os.access(executable, os.X_OK)
                or file_sha256(executable).lower() != target[hash_field].lower()):
            fail(f"configured {description} executable failed its SHA-256 check")
        return executable

    def xdotool(self, target: dict, *arguments: str,
                timeout: float = 10.0, check: bool = True) -> subprocess.CompletedProcess:
        executable = self.linux_tool(
            target, "xdotoolExecutable", "xdotoolSha256", "xdotool")
        result = subprocess.run(
            [str(executable), *arguments], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            check=False, env=self.runtime_environment(target, visual_driver=True),
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            fail("xdotool command failed" + (f": {detail}" if detail else ""))
        return result

    def linux_window(self, target: dict, pid: int, *,
                     timeout_seconds: float = 30.0) -> tuple[str, dict[str, int]]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            result = self.xdotool(
                target, "search", "--onlyvisible", "--pid", str(pid), check=False)
            pid_windows = {line.strip() for line in result.stdout.splitlines()
                           if line.strip().isdigit()}
            # Qt tags multiple visible render/helper children with Interface's
            # PID. The EWMH active window is the compositor-managed top-level;
            # intersect it with the PID-scoped search before accepting it.
            active_result = self.xdotool(target, "getactivewindow", check=False)
            active = active_result.stdout.strip()
            if active_result.returncode != 0 or active not in pid_windows:
                time.sleep(0.25)
                continue
            geometry_result = self.xdotool(
                target, "getwindowgeometry", "--shell", active, check=False)
            if geometry_result.returncode != 0:
                time.sleep(0.25)
                continue
            geometry: dict[str, int] = {}
            for line in geometry_result.stdout.splitlines():
                name, separator, value = line.partition("=")
                if separator and name in {"X", "Y", "WIDTH", "HEIGHT"}:
                    try:
                        geometry[name] = int(value)
                    except ValueError:
                        geometry = {}
                        break
            if (geometry.get("WIDTH", 0) >= 100
                    and geometry.get("HEIGHT", 0) >= 100):
                return active, geometry
            time.sleep(0.25)
        fail("launched Overte process has no visible X11 window")

    def linux_activate_window(self, target: dict, window: str) -> None:
        """Activate one already PID-resolved window and let Qt observe it."""
        self.xdotool(target, "windowactivate", "--sync", window)
        # Mutter/Xwayland focus is asynchronous with respect to Qt activation even
        # after xdotool observes the WM activation. Give the application one
        # bounded event-loop interval before global XTEST input.
        time.sleep(0.35)

    def linux_visual_action(self, target: dict, action: str, values: dict) -> None:
        if target.get("inputDriver") == "wayland-libei":
            self.wayland_visual_action(target, action, values)
            return
        if target.get("inputDriver") != "xdotool" or not target.get("isolatedX11"):
            fail("xdotool input is restricted to adapter-owned isolated X11 targets")
        pid = int(values.get("processId", 0))
        if pid <= 0:
            fail("Linux visual action requires a launched Overte process ID")
        # Keep cleanup bounded if the compositor is between focus states. A
        # failed graceful close falls through to owned process-group cleanup.
        if action == "close":
            window, geometry = self.linux_window(
                target, pid, timeout_seconds=1.0)
        else:
            window, geometry = self.linux_window(target, pid)
        # This path is restricted above to the adapter-owned GPU Xwayland
        # session. Ask the WM to activate the exact selected PID window so
        # Qt's Application::hasFocus() becomes true. Do not follow this with
        # XSetInputFocus: compositor correction of raw focus can emit the
        # FocusOut that clears Overte's held keyboard state.
        self.linux_activate_window(target, window)
        width, height = geometry["WIDTH"], geometry["HEIGHT"]
        if action == "focus":
            return
        if action == "look":
            horizontal = float(values.get("horizontal", 0.25))
            vertical = float(values.get("vertical", 0.0))
            center_x, center_y = width // 2, height // 2
            destination_x = center_x - int(width * horizontal)
            destination_y = center_y - int(height * vertical)
            self.xdotool(target, "mousemove", "--window", window,
                         str(center_x), str(center_y))
            self.xdotool(target, "mousedown", "3")
            try:
                for step in range(1, 9):
                    x = center_x + int((destination_x - center_x) * step / 8.0)
                    y = center_y + int((destination_y - center_y) * step / 8.0)
                    self.xdotool(target, "mousemove", "--window", window,
                                 str(x), str(y))
                    time.sleep(0.05)
            finally:
                self.xdotool(target, "mouseup", "3")
            return
        if action in {"fly", "jump", "move", "settle", "tablet-close", "tablet-open"}:
            keys = {
                "fly": "jump", "jump": "jump", "settle": "down",
                "tablet-close": "tablet", "tablet-open": "tablet",
            }
            key = (values.get("direction") if action == "move" else keys[action])
            if key not in {"backward", "down", "forward", "jump",
                           "left", "right", "tablet"}:
                fail("unsupported controlled keyboard action")
            durations = {"jump": 0.1, "settle": 2.5,
                         "tablet-close": 0.1, "tablet-open": 0.1}
            duration = float(values.get(
                "durationSeconds", durations.get(action, 1.5)))
            selector = self.selector_for_target(target)
            state = self.read_state(selector)
            if not state or state.get("pid") != pid or not self.state_alive(state):
                fail("controlled keyboard action requires the launched process")
            self.controlled_key_hold(selector, target, state, key, duration)
            return
        if action == "close":
            self.xdotool(target, "windowclose", window)
            return
        fail(f"unsupported Linux visual action: {action}")

    def wayland_visual_action(self, target: dict, action: str, values: dict) -> None:
        pid = int(values.get("processId", 0))
        if pid <= 0:
            fail("Wayland visual action requires a launched Overte process ID")
        try:
            client = self.wayland_input_client(target)
            status = client.status()
            if not all(status.values()):
                fail("Wayland input daemon has incomplete input capabilities")
            if action == "focus":
                # Visible debug runs are operator-coordinated. No synthetic
                # desktop focus or activation operation is performed here.
                return
            if action == "look":
                size = target["desktopSize"]
                dx = -float(size["width"]) * float(values.get("horizontal", 0.25))
                dy = -float(size["height"]) * float(values.get("vertical", 0.0))
                client.button(273, "down")  # BTN_RIGHT
                try:
                    for _ in range(8):
                        client.motion(dx / 8.0, dy / 8.0)
                        time.sleep(0.05)
                finally:
                    client.button(273, "up")
                return
            if action == "move":
                keys = {"forward": 17, "backward": 31, "left": 30, "right": 32}
                direction = values.get("direction", "forward")
                if direction not in keys:
                    fail("unsupported movement direction")
                key = keys[direction]
                client.key(key, "down")
                try:
                    time.sleep(float(values.get("durationSeconds", 1.5)))
                finally:
                    client.key(key, "up")
                return
            if action in {"fly", "jump", "settle"}:
                keys = {"fly": 57, "jump": 57, "settle": 46}
                durations = {"jump": 0.1, "settle": 2.5}
                client.key(keys[action], "down")
                try:
                    time.sleep(float(values.get(
                        "durationSeconds", durations.get(action, 1.5))))
                finally:
                    client.key(keys[action], "up")
                return
            if action == "tablet-open":
                client.key(15, "down")  # KEY_TAB / Actions.ContextMenu
                try:
                    time.sleep(0.1)
                finally:
                    client.key(15, "up")
                return
            if action == "tablet-close":
                client.key(15, "down")  # KEY_TAB / Actions.ContextMenu
                try:
                    time.sleep(0.1)
                finally:
                    client.key(15, "up")
                return
            if action == "close":
                client.key(56, "down")  # KEY_LEFTALT
                try:
                    client.key(62, "tap")  # KEY_F4
                finally:
                    client.key(56, "up")
                return
            fail(f"unsupported Wayland visual action: {action}")
        except WaylandInputError as error:
            fail(f"Wayland/libei input failed: {error}")

    def visual_action(self, target: dict, action: str, values: dict) -> None:
        self.linux_visual_action(target, action, values)

    def linux_screenshot(self, target: dict, pid: int, destination: Path) -> None:
        if not target.get("isolatedX11") or target.get("inputDriver") != "xdotool":
            fail("Linux screenshots are restricted to the isolated X11 target")
        executable = self.linux_tool(
            target, "screenshotExecutable", "screenshotSha256", "screenshot")
        window, _ = self.linux_window(target, pid)
        result = subprocess.run(
            [str(executable), *target.get("screenshotArguments", []),
             "-window", window, str(destination)], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
            env=self.runtime_environment(target, visual_driver=True),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            fail("Linux screenshot failed" + (f": {detail}" if detail else ""))

    def invoke(self, selector: str, operation: str, values: dict) -> dict:
        target = self.target(selector)
        values = validate_operation_arguments(operation, values)
        if operation == "app.launch":
            return self.launch(selector, target)
        state = self.read_state(selector)
        running = bool(state and self.state_alive(state))
        if operation == "app.process":
            return {"running": running, "identity": state["identity"] if running else None}
        if operation == "app.stop":
            self.cleanup(selector)
            return {"stopped": True}
        if not running:
            fail("Overte desktop process is not running")
        if operation == "app.foreground":
            if target.get("isolatedX11"):
                # Window.hasFocus() is not reliable in a private Xwayland
                # compositor. linux_window() independently requires the
                # EWMH-active, PID-owned top-level before activation succeeds.
                self.visual_action(target, "focus", {"processId": state["pid"]})
                return {"foreground": True}
            probe = target.get("probe")
            if probe:
                try:
                    foreground = read_fresh_json(self.probe_path(selector, target))["application"]["foreground"]
                except (KeyError, TypeError):
                    fail("desktop probe has no foreground state")
                return {"foreground": foreground is True}
            self.visual_action(target, "focus", {"processId": state["pid"]})
            return {"foreground": True}
        if operation == "probe.snapshot":
            return self.probe_snapshot(
                selector, target, state, values.get("afterSampleSequence"))
        if operation == "navigation.enter-domain":
            self.write_client_command(selector, target, state, {
                "schemaVersion": 1,
                "commandId": "navigation-" + uuid.uuid4().hex,
                "action": "navigate",
                "url": values["url"],
            })
            return {"requested": True}
        if operation == "asset.load":
            self.controlled_http_url(values["url"], "asset.load url")
            self.write_client_command(selector, target, state, {
                "schemaVersion": 1,
                "commandId": "asset-" + hashlib.sha256(json.dumps(
                    values, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")).hexdigest(),
                "action": "asset-load",
                **values,
            })
            return {"requested": True}
        if operation == "sound.play":
            return self.request_sound(selector, target, state, values)
        if operation == "scene.load":
            url = values.get("url")
            if not isinstance(url, str) or "://" not in url:
                fail("scene.load requires an absolute URL")
            if state.get("initialSceneUrl") != url:
                fail("desktop scene URL must match app.launch; live relaunch is forbidden")
            self.write_client_command(selector, target, state, {
                "schemaVersion": 1,
                "commandId": "scene-" + uuid.uuid4().hex,
                "action": "scene-load",
                "url": url,
            })
            self.settle_controlled_scene(
                selector, target, state, time.monotonic() + 5.0)
            return {"requested": True, "lifecycle": "same-process"}
        if operation == "input.look":
            horizontal = values.get("horizontal", 0.25)
            vertical = values.get("vertical", 0.0)
            if (not all(isinstance(item, (int, float)) and not isinstance(item, bool)
                        and math.isfinite(float(item)) for item in (horizontal, vertical))
                    or abs(float(horizontal)) > 0.45 or abs(float(vertical)) > 0.45):
                fail("desktop look input must use finite fractions from -0.45 through 0.45")
            self.controlled_look(selector, target, state, values)
            return {"performed": True}
        if operation == "input.move":
            duration = values.get("durationSeconds", 1.5)
            if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                    or not math.isfinite(float(duration)) or not 0.05 <= duration <= 10.0):
                fail("desktop movement duration must be from 0.05 through 10 seconds")
            self.visual_action(target, "move", {**values, "processId": state["pid"]})
            return {"performed": True}
        if operation == "input.jump":
            self.visual_action(target, "jump", {"processId": state["pid"]})
            return {"performed": True}
        if operation == "input.fly":
            self.visual_action(target, "fly", {**values, "processId": state["pid"]})
            return {"performed": True}
        if operation in {"tablet.open", "tablet.close"}:
            if not target.get("probe"):
                fail("desktop tablet operation requires the in-client probe")
            desired = operation.endswith("open")
            try:
                opened = read_fresh_json(self.probe_path(selector, target))["tablet"]["open"]
            except (KeyError, TypeError):
                fail("desktop probe has no tablet state")
            if not isinstance(opened, bool):
                fail("desktop probe tablet state is invalid")
            initial = opened
            if opened is not desired:
                deadline = time.monotonic() + 5.0
                for attempt in range(3):
                    action = "tablet-open" if desired else "tablet-close"
                    self.visual_action(target, action, {
                        "processId": state["pid"],
                        "normalizeKeyUp": attempt > 0,
                    })
                    # Probe-gate every retry.  This prevents a delayed
                    # successful toggle from being toggled back by the next
                    # pulse while keeping the complete retry sequence bounded.
                    for _ in range(10):
                        current = read_fresh_json(
                            self.probe_path(selector, target))["tablet"]["open"]
                        if not isinstance(current, bool):
                            fail("desktop probe tablet state is invalid")
                        opened = current
                        if opened is desired or time.monotonic() >= deadline:
                            break
                        time.sleep(0.1)
                    if opened is desired or time.monotonic() >= deadline:
                        break
                if opened is not desired:
                    fail("desktop Tab action did not reach the requested tablet state")
            return {"performed": True, "changed": initial is not desired}
        if operation == "artifact.screenshot":
            artifact_dir = os.environ.get("OVERTE_DEVICE_ARTIFACT_DIR")
            if not artifact_dir:
                fail("screenshot operation requires an artifact directory")
            screenshot = Path(artifact_dir) / "screenshot.png"
            screenshot.unlink(missing_ok=True)
            self.linux_screenshot(target, state["pid"], screenshot)
            if not screenshot.is_file() or screenshot.stat().st_size == 0:
                fail("Linux capture did not create a non-empty requested screenshot")
            screenshot.chmod(0o600)
            return {"artifact": "screenshot.png"}
        fail(f"unsupported operation: {operation}")

    def cleanup(self, selector: str) -> dict:
        target = self.target(selector)
        state = self.read_state(selector)
        if state and self.state_alive(state):
            try:
                self.visual_action(target, "close", {"processId": state["pid"]})
            except RuntimeError:
                pass
            deadline = time.monotonic() + 5
            while self.state_alive(state) and time.monotonic() < deadline:
                time.sleep(0.1)
        if state and self.process_tree_alive(state):
            try:
                self.terminate_process_tree(state["pid"], force=False)
            except OSError:
                pass
            deadline = time.monotonic() + 5
            while self.process_tree_alive(state) and time.monotonic() < deadline:
                time.sleep(0.1)
            if self.process_tree_alive(state):
                try:
                    self.terminate_process_tree(state["pid"], force=True)
                except OSError:
                    pass
                deadline = time.monotonic() + 5
                while self.process_tree_alive(state) and time.monotonic() < deadline:
                    time.sleep(0.1)
            if self.process_tree_alive(state):
                fail("Overte desktop process could not be terminated")
        self.state_path(selector).unlink(missing_ok=True)
        self.probe_script_path(selector).unlink(missing_ok=True)
        if target.get("isolatedX11"):
            self.gpu_headless_lifecycle(target).cleanup()
        if target.get("inputDriver") == "wayland-libei":
            self.stop_wayland_input(selector, target)
        return {"cleaned": True}


def main() -> int:
    args = cli()
    adapter = LinuxAdapter()
    if args.action == "discover":
        emit(adapter.discover())
        return 0
    if not args.target:
        fail(f"{args.action} requires --target")
    if args.action == "describe":
        emit(adapter.describe(args.target))
    elif args.action == "cleanup":
        emit(adapter.cleanup(args.target))
    elif args.action == "authorize-input":
        emit(adapter.ensure_wayland_input(
            args.target, adapter.target(args.target), authorize=True))
    else:
        if not args.operation:
            fail("invoke requires --operation")
        emit(adapter.invoke(args.target, args.operation,
                            parse_operation_arguments(args.arguments)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
