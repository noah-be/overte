#!/usr/bin/env python3
"""Windows desktop adapter with target-scoped OculiX automation."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
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
from contracts import validate_operation_arguments  # noqa: E402


DRIVER = Path(__file__).resolve().parent / "overte.sikuli"
PROBE_SCRIPT = DEVICE_ROOT / "probe" / "overte_e2e_probe.js"
HASH_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
WINDOWS_CHILD_ENVIRONMENT = frozenset({
    "ALLUSERSPROFILE", "APPDATA", "COMMONPROGRAMFILES",
    "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "COMSPEC",
    "HOMEDRIVE", "HOMEPATH", "JAVA_HOME", "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS", "ONEDRIVE", "OS", "PATH", "PATHEXT",
    "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "PROCESSOR_LEVEL",
    "PROCESSOR_REVISION", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "PROGRAMW6432", "PUBLIC", "SESSIONNAME",
    "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "USERDOMAIN",
    "USERDOMAIN_ROAMINGPROFILE", "USERNAME", "USERPROFILE", "WINDIR",
})
PRIVATE_CHILD_ENVIRONMENT = frozenset({
    "GH_TOKEN", "GITHUB_TOKEN", "HIFI_ALLOW_MULTIPLE_INSTANCES",
    "OVERTE_DEVICE_ADAPTER_MANIFEST", "OVERTE_DEVICE_ARTIFACT_DIR",
    "OVERTE_DEVICE_STATE_ROOT", "OVERTE_DEVICE_TARGET_SELECTOR",
    "OVERTE_E2E_SCENE_URL", "OVERTE_WINDOWS_TARGETS",
})


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("discover", "describe", "invoke", "cleanup"))
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


class WindowsAdapter:

    def __init__(self) -> None:
        self.adapter_id = "windows-desktop"
        self.targets = self.load_targets()

    def require_interactive_host(self) -> None:
        physical = any(
            target.get("physical") is True and target.get("enabled", True)
            for target in self.targets.values()
        )
        if not physical:
            return
        if os.name != "nt":
            fail("physical Windows desktop targets require a Windows host")
        from ctypes import wintypes
        session_id = wintypes.DWORD()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcessId.restype = wintypes.DWORD
        kernel32.ProcessIdToSessionId.argtypes = [
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
        if not kernel32.ProcessIdToSessionId(
                kernel32.GetCurrentProcessId(), ctypes.byref(session_id)):
            fail("Windows desktop session could not be identified")
        if session_id.value == 0:
            fail("Windows OculiX targets cannot run in non-interactive Session 0")
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        desktop_read_objects = 0x0001
        desktop_switch_desktop = 0x0100
        user32.OpenInputDesktop.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
        ]
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        user32.CloseDesktop.restype = wintypes.BOOL
        desktop = user32.OpenInputDesktop(
            0, False, desktop_read_objects | desktop_switch_desktop)
        if not desktop:
            fail("Windows OculiX targets require access to the active input desktop")
        user32.CloseDesktop(desktop)

    def load_targets(self) -> dict[str, dict]:
        config_value = os.environ.get("OVERTE_WINDOWS_TARGETS")
        if not config_value:
            fail("OVERTE_WINDOWS_TARGETS must name a private target configuration")
        payload = json.loads(expanded_path(config_value).read_text(encoding="utf-8"))
        entries = payload.get("targets")
        if payload.get("schemaVersion") != 1 or not isinstance(entries, list):
            fail("unsupported Windows target configuration schema")
        targets: dict[str, dict] = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("platform") != "windows":
                fail("Windows target configuration contains a non-Windows target")
            selector = entry.get("selector")
            if (not isinstance(selector, str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", selector)
                    or selector in targets):
                fail("Windows target selectors must be unique bounded identifiers")
            if not all(isinstance(entry.get(field), str) and entry[field]
                       and "\x00" not in entry[field]
                       for field in ("executable", "windowTitle", "oculixJar",
                                     "javaExecutable")):
                fail("Windows target requires safe executable, window, OculiX and Java values")
            if len(entry["windowTitle"]) > 200 or any(
                    ord(character) < 32 for character in entry["windowTitle"]):
                fail("Windows target windowTitle must be a bounded printable string")
            for field in ("executableSha256", "oculixSha256", "javaSha256"):
                if not isinstance(entry.get(field), str) or not HASH_PATTERN.fullmatch(
                        entry[field]):
                    fail(f"Windows target {field} must contain 64 hexadecimal digits")
            for field in ("arguments", "javaArguments"):
                if not isinstance(entry.get(field, []), list) or not all(
                        isinstance(item, str) and "\x00" not in item
                        for item in entry.get(field, [])):
                    fail(f"Windows target {field} must be a NUL-free string list")
            environment = entry.get("environment", {})
            if (not isinstance(environment, dict) or not all(
                    isinstance(key, str) and re.fullmatch(
                        r"[A-Za-z_][A-Za-z0-9_]*", key)
                    and isinstance(value, str) and "\x00" not in value
                    for key, value in environment.items())):
                fail("Windows target environment must contain safe string assignments")
            probe = entry.get("probe")
            if probe is not None:
                if not isinstance(probe, dict) or probe.get("kind") not in {
                        "host-file", "injected-test-script"}:
                    fail("Windows probe must use a supported transport")
                if (probe["kind"] == "host-file"
                        and (not isinstance(probe.get("path"), str)
                             or not probe["path"] or "\x00" in probe["path"])):
                    fail("Windows host-file probe requires a safe path")
            control = entry.get("clientControl")
            if control is not None:
                if control != {"kind": "fixture-command-http"}:
                    fail("Windows clientControl must select fixture-command-http")
                if not isinstance(probe, dict) or probe.get("kind") != "injected-test-script":
                    fail("Windows clientControl requires the injected in-client probe")
            for field in ("physical", "enabled"):
                if field in entry and not isinstance(entry[field], bool):
                    fail(f"Windows target {field} must be boolean")
            working = entry.get("workingDirectory")
            if working is not None and (not isinstance(working, str)
                                        or not working or "\x00" in working):
                fail("Windows target workingDirectory must be a safe path")
            targets[selector] = entry
        return targets

    @staticmethod
    def capabilities(target: dict) -> list[str]:
        values = [
            "app.foreground", "app.launch", "app.process", "app.stop",
            "artifact.screenshot", "input.fly", "input.jump", "input.look",
            "input.move",
        ]
        if target.get("probe"):
            values += ["probe.snapshot", "tablet.close", "tablet.open"]
        if WindowsAdapter.controlled_client(target):
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
        for target in self.targets.values():
            if target.get("enabled", True):
                self.validate_target_tools(target)
        return [{
            "selector": selector,
            "displayName": target.get("displayName", "Overte Windows"),
            "platform": "windows",
            "physical": target.get("physical") is True,
            "capabilities": self.capabilities(target),
        } for selector, target in sorted(self.targets.items()) if target.get("enabled", True)]

    def target(self, selector: str) -> dict:
        target = self.targets.get(selector)
        if not target or not target.get("enabled", True):
            fail("requested desktop target is not configured")
        return target

    def selector_for_target(self, target: dict) -> str:
        for selector, candidate in self.targets.items():
            if candidate is target:
                return selector
        fail("Windows desktop target identity is not configured")

    @staticmethod
    def configured_file(
            target: dict, path_field: str, hash_field: str,
            description: str, *, executable: bool = False) -> Path:
        path = expanded_path(target[path_field])
        if not path.is_file():
            fail(f"configured {description} was not found")
        if executable and os.name != "nt" and not os.access(path, os.X_OK):
            fail(f"configured {description} is not executable")
        if file_sha256(path).lower() != target[hash_field].lower():
            fail(f"configured {description} failed its SHA-256 check")
        return path

    @classmethod
    def validate_target_tools(cls, target: dict) -> None:
        cls.configured_file(
            target, "executable", "executableSha256", "Overte executable",
            executable=True)
        cls.configured_file(
            target, "oculixJar", "oculixSha256", "OculiX runtime JAR")
        cls.configured_file(
            target, "javaExecutable", "javaSha256", "Java executable",
            executable=True)

    def target_environment(
            self, target: dict, *, visual_driver: bool = False) -> dict[str, str]:
        del visual_driver
        environment = {
            key: value for key, value in os.environ.items()
            if key.upper() in WINDOWS_CHILD_ENVIRONMENT
        }
        environment.update(target.get("environment", {}))
        for name in list(environment):
            if (name.upper() in PRIVATE_CHILD_ENVIRONMENT
                    or name.upper().startswith(("JENKINS_", "GITHUB_"))):
                environment.pop(name, None)
        return environment

    def runtime_environment(
            self, target: dict, *, visual_driver: bool = False,
            start_isolated: bool = False) -> dict[str, str]:
        del start_isolated
        return self.target_environment(target, visual_driver=visual_driver)

    def describe(self, selector: str) -> dict:
        target = self.target(selector)
        return {
            "adapter": self.adapter_id,
            "model": target.get("model", "physical desktop"),
            "os": "windows",
            "osVersion": target.get("osVersion"),
            "role": "physical-desktop-e2e",
        }

    def state_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "process.json"

    def read_state(self, selector: str) -> dict | None:
        path = self.state_path(selector)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            fail("Windows desktop process state has an unsafe file type")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("Windows desktop process state is invalid")
        if (not isinstance(value, dict)
                or not isinstance(value.get("pid"), int)
                or isinstance(value.get("pid"), bool)
                or value["pid"] <= 0
                or not isinstance(value.get("processToken"), str)
                or not value["processToken"]
                or value.get("identity") != f'{value["pid"]}:{value["processToken"]}'
                or value.get("schemaVersion") not in (None, 2)
                or (value.get("schemaVersion") == 2
                    and (not isinstance(value.get("executablePath"), str)
                         or not value["executablePath"]))
                or (value.get("initialSceneUrl") is not None
                    and not isinstance(value.get("initialSceneUrl"), str))):
            fail("Windows desktop process state is invalid")
        return value

    @staticmethod
    def process_identity(pid: int) -> tuple[str, str] | None:
        from ctypes import wintypes
        synchronize = 0x00100000
        query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            synchronize | query_limited_information, False, pid)
        if not handle:
            return None
        try:
            if kernel32.WaitForSingleObject(handle, 0) != 0x00000102:
                return None
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                    handle, ctypes.byref(creation), ctypes.byref(exit_time),
                    ctypes.byref(kernel), ctypes.byref(user)):
                return None
            length = wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(length.value)
            if not kernel32.QueryFullProcessImageNameW(
                    handle, 0, image, ctypes.byref(length)):
                return None
            token = str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
            return token, str(Path(image.value).resolve())
        finally:
            kernel32.CloseHandle(handle)

    @classmethod
    def process_token(cls, pid: int) -> str | None:
        identity = cls.process_identity(pid)
        return identity[0] if identity else None

    @staticmethod
    def process_snapshot() -> dict[int, int]:
        """Return the current Windows PID-to-parent map from Toolhelp."""
        from ctypes import wintypes

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(ProcessEntry)
        ]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(ProcessEntry)
        ]
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        invalid_handle = ctypes.c_void_p(-1).value
        if snapshot in (None, invalid_handle):
            fail("Windows process tree could not be enumerated")
        processes: dict[int, int] = {}
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(ProcessEntry)
            available = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while available:
                processes[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                available = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return processes

    @classmethod
    def owned_processes(cls, state: dict) -> list[dict[str, object]]:
        """Capture exact live identities for the root and all current children."""
        root_pid = state["pid"]
        parents = cls.process_snapshot()
        descendants = {root_pid}
        changed = True
        while changed:
            changed = False
            for pid, parent in parents.items():
                if parent in descendants and pid not in descendants:
                    descendants.add(pid)
                    changed = True
        owned: list[dict[str, object]] = []
        for pid in sorted(descendants):
            identity = cls.process_identity(pid)
            if identity is None:
                continue
            token, executable = identity
            if pid == root_pid and token != state.get("processToken"):
                continue
            owned.append({
                "pid": pid,
                "processToken": token,
                "executablePath": executable,
            })
        return owned

    @classmethod
    def owned_process_alive(cls, process: dict[str, object]) -> bool:
        return cls.alive(
            int(process["pid"]), str(process["processToken"]),
            str(process["executablePath"]))

    @classmethod
    def alive(
            cls, pid: int, expected_token: str | None = None,
            expected_executable: str | None = None) -> bool:
        observed = cls.process_identity(pid)
        if observed is None:
            return False
        token, executable = observed
        return ((expected_token is None or token == expected_token)
                and (expected_executable is None or os.path.normcase(executable)
                     == os.path.normcase(str(Path(expected_executable).resolve()))))

    @classmethod
    def state_alive(cls, state: dict) -> bool:
        token = state.get("processToken")
        executable = state.get("executablePath")
        return (isinstance(token, str) and bool(token)
                and (executable is None or isinstance(executable, str))
                and cls.alive(state["pid"], token, executable))

    @classmethod
    def process_tree_alive(cls, state: dict) -> bool:
        return cls.state_alive(state)

    @staticmethod
    def terminate_process_tree(pid: int, *, force: bool) -> None:
        taskkill = "taskkill"
        if os.name == "nt":
            system_root = os.environ.get("SystemRoot")
            if not system_root:
                fail("Windows SystemRoot is unavailable for process cleanup")
            trusted = Path(system_root) / "System32" / "taskkill.exe"
            if not trusted.is_file():
                fail("trusted Windows taskkill.exe was not found")
            taskkill = str(trusted)
        command = [taskkill, "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15, check=False,
        )

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
            fail("Windows desktop client command exceeds the fixture limit")
        request = Request(
            self.client_command_endpoint(scene_url), data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                fail("controlled fixture rejected the Windows desktop client command")
            encoded = response.read(4097)
        if len(encoded) > 4096:
            fail("controlled fixture returned an oversized client command response")
        try:
            accepted = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "controlled fixture returned an invalid client command response") from error
        if accepted != command:
            fail("controlled fixture did not acknowledge the exact Windows client command")

    def write_client_command(
            self, selector: str, target: dict, state: dict, command: dict) -> None:
        if not self.controlled_client(target):
            fail("desktop operation requires the controlled in-client probe channel")
        if not self.state_alive(state):
            fail("Overte desktop process changed before the in-client command")
        scene_url = state.get("initialSceneUrl")
        if not isinstance(scene_url, str):
            fail("Windows in-client command channel requires the controlled scene origin")
        self.post_client_command(scene_url, command)
        if not self.state_alive(state):
            fail("Overte desktop process changed while delivering the in-client command")

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
        if not target.get("probe"):
            self.visual_action(target, "look", {**values, "processId": state["pid"]})
            return
        before = read_fresh_json(self.probe_path(selector, target))
        orientation = before.get("view", {}).get("orientation", {})
        horizontal = float(values["horizontal"])
        vertical = float(values["vertical"])
        axis = "y" if abs(horizontal) >= abs(vertical) else "x"
        requested = horizontal if axis == "y" else vertical
        requested_sign = 1.0 if requested > 0.0 else -1.0
        baseline = orientation.get(axis)
        sequence = before.get("sampleSequence")
        if (not isinstance(baseline, (int, float)) or isinstance(baseline, bool)
                or not isinstance(sequence, int) or isinstance(sequence, bool)):
            fail("Windows probe has no usable look orientation")
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
        fail("Windows look input did not produce the requested camera rotation")

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
                if time.monotonic() < observe_after_monotonic:
                    time.sleep(0.1)
                    continue
                if avatar.get("inAir") is False and avatar.get("flying") is False:
                    return
                if not requested_grounding:
                    self.visual_action(target, "settle", {"processId": state["pid"]})
                    requested_grounding = True
            time.sleep(0.1)
        fail("controlled Windows scene did not reach a grounded spawn")

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
        temporary.chmod(0o600)
        temporary.replace(path)

    def launch(self, selector: str, target: dict) -> dict:
        state = self.read_state(selector)
        if state and self.state_alive(state):
            expected = str(self.configured_file(
                target, "executable", "executableSha256", "Overte executable",
                executable=True))
            if (state.get("schemaVersion") == 2
                    and os.path.normcase(state.get("executablePath", ""))
                    == os.path.normcase(expected)):
                self.visual_action(target, "focus", {"processId": state["pid"]})
                return {"launched": True}
            self.cleanup(selector)
        elif state:
            self.cleanup(selector)
        self.require_interactive_host()
        self.validate_target_tools(target)
        executable = self.configured_file(
            target, "executable", "executableSha256", "Overte executable",
            executable=True)
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
            if self.controlled_client(target):
                self.controlled_http_url(
                    initial_scene_url, "controlled OVERTE_E2E_SCENE_URL")
            # Loading the fixture as part of the one authoritative process is
            # intentional. Starting Interface again merely to forward --url
            # can race its local socket, display a second mode selector, and
            # makes process lifecycle assertions ambiguous.
            arguments += ["--url", initial_scene_url]
        elif self.controlled_client(target):
            fail("controlled Windows targets require OVERTE_E2E_SCENE_URL")
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
            log.chmod(0o600)
            process = subprocess.Popen(
                arguments,
                cwd=working,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=self.runtime_environment(target),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        identity = self.process_identity(process.pid)
        if identity is None:
            process.terminate()
            fail("launched Overte process could not be identified")
        token, observed_executable = identity
        if os.path.normcase(observed_executable) != os.path.normcase(str(executable)):
            process.terminate()
            fail("launched Windows process does not match the configured executable")
        state = {"schemaVersion": 2, "pid": process.pid, "processToken": token,
                 "identity": f"{process.pid}:{token}",
                 "executablePath": str(executable),
                 "initialSceneUrl": initial_scene_url}
        self.save_state(selector, state)
        try:
            self.visual_action(target, "focus", {"processId": process.pid})
        except RuntimeError:
            self.cleanup(selector)
            raise
        return {"launched": True}

    def oculix(self, target: dict, action: str, values: dict) -> None:
        self.require_interactive_host()
        jar = self.configured_file(
            target, "oculixJar", "oculixSha256", "OculiX runtime JAR")
        java = self.configured_file(
            target, "javaExecutable", "javaSha256", "Java executable",
            executable=True)
        arguments = dict(values)
        arguments["windowTitle"] = target["windowTitle"]
        environment = self.runtime_environment(target, visual_driver=True)
        command = [str(java), *target.get("javaArguments", []), "-jar", str(jar),
                   "-r", str(DRIVER), "--", action,
                   json.dumps(arguments, separators=(",", ":"))]
        try:
            result = subprocess.run(
                command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=60, check=False, env=environment,
            )
        except subprocess.TimeoutExpired:
            self.release_oculix_input(target, java, jar, environment)
            fail(f"OculiX action {action} timed out after 60 seconds")
        if result.returncode != 0:
            if action != "release-input":
                self.release_oculix_input(target, java, jar, environment)
            streams = []
            if result.stdout.strip():
                streams.append("stdout:\n" + result.stdout.strip())
            if result.stderr.strip():
                streams.append("stderr:\n" + result.stderr.strip())
            raw_detail = "\n".join(streams)
            for field in ("executable", "workingDirectory", "oculixJar",
                          "javaExecutable"):
                private_value = target.get(field)
                if isinstance(private_value, str) and private_value:
                    raw_detail = raw_detail.replace(private_value, "<private-path>")
                    raw_detail = raw_detail.replace(
                        str(expanded_path(private_value)), "<private-path>")
            detail = raw_detail if len(raw_detail) <= 6000 else (
                raw_detail[:3000] + "\n... OculiX output truncated ...\n" + raw_detail[-3000:]
            )
            fail(f"OculiX action {action} failed" + (f": {detail}" if detail else ""))

    def release_oculix_input(
            self, target: dict, java: Path, jar: Path,
            environment: dict[str, str]) -> None:
        arguments = {"windowTitle": target["windowTitle"]}
        try:
            subprocess.run(
                [str(java), *target.get("javaArguments", []), "-jar", str(jar),
                 "-r", str(DRIVER), "--", "release-input",
                 json.dumps(arguments, separators=(",", ":"))],
                text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=15, check=False, env=environment,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def visual_action(self, target: dict, action: str, values: dict) -> None:
        pid = values.get("processId")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            fail("Windows visual action requires the launched Overte process ID")
        selector = self.selector_for_target(target)
        state = self.read_state(selector)
        if (not state or state.get("pid") != pid or not self.state_alive(state)):
            fail("Windows visual action requires the authoritative Overte process")
        self.oculix(target, action, values)
        if action != "close" and not self.state_alive(state):
            fail("Overte desktop process changed during the Windows visual action")

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
            url = values["url"]
            if state.get("initialSceneUrl") != url:
                fail("Windows scene URL must match app.launch; live relaunch is forbidden")
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
            artifact_root = Path(artifact_dir)
            if artifact_root.is_symlink() or not artifact_root.is_dir():
                fail("screenshot artifact directory has an unsafe file type")
            artifact_root = artifact_root.resolve()
            screenshot = artifact_root / "screenshot.png"
            screenshot.unlink(missing_ok=True)
            self.visual_action(target, "screenshot", {
                "artifactDirectory": str(artifact_root),
                "filename": "screenshot.png",
                "processId": state["pid"],
            })
            if not screenshot.is_file() or screenshot.stat().st_size == 0:
                fail("OculiX did not create a non-empty requested screenshot")
            screenshot.chmod(0o600)
            return {"artifact": "screenshot.png"}
        fail(f"unsupported operation: {operation}")

    def cleanup(self, selector: str) -> dict:
        target = self.target(selector)
        state = self.read_state(selector)
        owned: list[dict[str, object]] = []
        if state and self.state_alive(state):
            owned = self.owned_processes(state)
            try:
                self.visual_action(target, "close", {"processId": state["pid"]})
            except RuntimeError:
                pass
            deadline = time.monotonic() + 5
            while self.state_alive(state) and time.monotonic() < deadline:
                time.sleep(0.1)
        for process in owned:
            if not self.owned_process_alive(process):
                continue
            try:
                self.terminate_process_tree(int(process["pid"]), force=False)
            except OSError:
                pass
        if owned:
            deadline = time.monotonic() + 5
            while (any(self.owned_process_alive(process) for process in owned)
                   and time.monotonic() < deadline):
                time.sleep(0.1)
            for process in owned:
                if not self.owned_process_alive(process):
                    continue
                try:
                    self.terminate_process_tree(int(process["pid"]), force=True)
                except OSError:
                    pass
            if any(self.owned_process_alive(process) for process in owned):
                deadline = time.monotonic() + 5
                while (any(self.owned_process_alive(process) for process in owned)
                       and time.monotonic() < deadline):
                    time.sleep(0.1)
            if any(self.owned_process_alive(process) for process in owned):
                fail("owned Windows desktop process tree could not be terminated")
        self.state_path(selector).unlink(missing_ok=True)
        self.probe_script_path(selector).unlink(missing_ok=True)
        return {"cleaned": True}


def main() -> int:
    args = cli()
    adapter = WindowsAdapter()
    if args.action == "discover":
        emit(adapter.discover())
        return 0
    if not args.target:
        fail(f"{args.action} requires --target")
    if args.action == "describe":
        emit(adapter.describe(args.target))
    elif args.action == "cleanup":
        emit(adapter.cleanup(args.target))
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
