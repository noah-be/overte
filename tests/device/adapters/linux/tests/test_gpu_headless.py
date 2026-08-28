#!/usr/bin/env python3
"""Device-free ownership, GPU and isolation tests for Mutter headless."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "adapters/linux/gpu_headless.py"
SPEC = importlib.util.spec_from_file_location("gpu_headless_under_test", MODULE_PATH)
GPU = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GPU)


FAKE_DBUS = r'''#!PYTHON
import json, os, pathlib, signal, subprocess, sys
separator = sys.argv.index("--")
with pathlib.Path(os.environ["FAKE_DBUS_LOG"]).open("a", encoding="utf-8") as output:
    output.write(json.dumps(sys.argv[1:]) + "\n")
environment = dict(os.environ)
environment["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + environment["XDG_RUNTIME_DIR"] + "/private-bus"
child = subprocess.Popen(sys.argv[separator + 1:], env=environment)
running = True
def stop(*_args):
    global running
    running = False
    try: child.terminate()
    except ProcessLookupError: pass
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
while running and child.poll() is None:
    try: child.wait(timeout=0.1)
    except subprocess.TimeoutExpired: pass
if child.poll() is None: child.terminate()
try: child.wait(timeout=2)
except subprocess.TimeoutExpired:
    child.kill()
    child.wait()
sys.exit(child.returncode or 0)
'''.replace("PYTHON", sys.executable)

FAKE_SESSION_GUARD = r'''#!PYTHON
import json, os, pathlib, signal, subprocess, sys
arguments = sys.argv[1:]
separator = arguments.index("--")
mutter = arguments[arguments.index("--mutter") + 1]
with pathlib.Path(os.environ["FAKE_GUARD_LOG"]).open("a", encoding="utf-8") as output:
    output.write(json.dumps(arguments) + "\n")
child = subprocess.Popen([mutter, *arguments[separator + 1:]], env=os.environ)
running = True
def stop(*_args):
    global running
    running = False
    try: child.terminate()
    except ProcessLookupError: pass
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
while running and child.poll() is None:
    try: child.wait(timeout=0.1)
    except subprocess.TimeoutExpired: pass
if child.poll() is None: child.terminate()
try: child.wait(timeout=2)
except subprocess.TimeoutExpired:
    child.kill()
    child.wait()
sys.exit(child.returncode or 0)
'''.replace("PYTHON", sys.executable)

FAKE_MUTTER = r'''#!PYTHON
import json, os, pathlib, signal, socket, subprocess, sys, time
arguments = sys.argv[1:]
with pathlib.Path(os.environ["FAKE_GPU_LOG"]).open("a", encoding="utf-8") as output:
    output.write(json.dumps({
        "arguments": arguments,
        "environment": {name: os.environ.get(name) for name in (
            "DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET",
            "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
            "GIO_USE_VFS", "GTK_USE_PORTAL", "QT_NO_XDG_DESKTOP_PORTAL",
            "GTK_A11Y",
            "LD_LIBRARY_PATH", "LIBGL_ALWAYS_SOFTWARE",
            "MESA_LOADER_DRIVER_OVERRIDE", "MUTTER_DEBUG_FAKE",
            "MUTTER_DEBUG_DUMMY_MODE_SPECS")}
    }) + "\n")
separator = arguments.index("--")
sentinel_command = arguments[separator + 1:]
wayland_name = next(item.split("=", 1)[1] for item in arguments
                    if item.startswith("--wayland-display="))
runtime = pathlib.Path(os.environ["XDG_RUNTIME_DIR"])
wayland_path = runtime / wayland_name
wayland_path.unlink(missing_ok=True)
listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
listener.bind(str(wayland_path))
os.chmod(wayland_path, 0o600)
listener.listen(1)
xauthority = runtime / ".mutter-Xwaylandauth.test"
xauthority.write_bytes(b"private-test-cookie")
os.chmod(xauthority, 0o600)
child_environment = dict(os.environ)
child_environment.update({
    "DISPLAY": ":1777", "XAUTHORITY": str(xauthority),
    "WAYLAND_DISPLAY": wayland_name,
})
xwaylands = [subprocess.Popen([
    os.environ["FAKE_XWAYLAND"], ":1777", "-auth", str(xauthority),
    *(["-enable-ei-portal"] if os.environ.get("FAKE_XWAYLAND_EI_PORTAL") == "1" else []),
], env=child_environment)]
if os.environ.get("FAKE_EXTRA_XWAYLAND") == "1":
    xwaylands.append(subprocess.Popen([
        os.environ["FAKE_XWAYLAND"], ":1777", "-auth", str(xauthority),
    ], env=child_environment))
sentinel = subprocess.Popen(sentinel_command, env=child_environment)
running = True
def stop(*_args):
    global running
    running = False
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    while (running and sentinel.poll() is None
           and all(child.poll() is None for child in xwaylands)):
        time.sleep(0.05)
finally:
    for child in (sentinel, *xwaylands):
        if child.poll() is None: child.terminate()
    for child in (sentinel, *xwaylands):
        try: child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    listener.close()
    wayland_path.unlink(missing_ok=True)
    xauthority.unlink(missing_ok=True)
'''.replace("PYTHON", sys.executable)

FAKE_XWAYLAND = r'''#!PYTHON
import signal, time
running = True
def stop(*_args):
    global running
    running = False
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
while running: time.sleep(0.05)
'''.replace("PYTHON", sys.executable)

FAKE_GLXINFO = r'''#!PYTHON
import os
if os.environ.get("LC_ALL") != "C" or os.environ.get("LANG") != "C":
    raise SystemExit("GPU proof tools require a stable C locale")
mode = os.environ.get("FAKE_GLX_MODE", "gpu")
direct = "No" if mode == "indirect" else "Yes"
vendor = "Mesa" if mode in {"software", "vendor"} else "Test GPU Vendor"
renderer = "llvmpipe (LLVM test)" if mode == "software" else (
    "Unexpected GPU" if mode == "renderer" else "Test GPU Renderer")
print("direct rendering: " + direct)
print("OpenGL vendor string: " + vendor)
print("OpenGL renderer string: " + renderer)
'''.replace("PYTHON", sys.executable)

FAKE_XRANDR = r'''#!PYTHON
import os
mode = os.environ.get("FAKE_XRANDR_MODE", "good")
if mode == "multi":
    print("Screen 0: minimum 16 x 16, current 1280 x 720, maximum 32767 x 32767")
    print("Meta-0 connected primary 1280x720+0+0")
    print("Meta-1 connected 1280x720+1280+0")
elif mode == "wrong":
    print("Screen 0: minimum 16 x 16, current 1024 x 768, maximum 32767 x 32767")
    print("Meta-0 connected primary 1024x768+0+0")
else:
    print("Screen 0: minimum 16 x 16, current 1280 x 720, maximum 32767 x 32767")
    print("Meta-0 connected primary 1280x720+0+0")
'''.replace("PYTHON", sys.executable)


class GpuHeadlessLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gpu-headless-test-")
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.tools = {}
        for name, source in (
                ("dbus", FAKE_DBUS), ("mutter", FAKE_MUTTER),
                ("session-guard", FAKE_SESSION_GUARD),
                ("Xwayland", FAKE_XWAYLAND), ("glxinfo", FAKE_GLXINFO),
                ("xrandr", FAKE_XRANDR)):
            path = self.root / name
            path.write_text(source, encoding="utf-8")
            path.chmod(0o700)
            self.tools[name] = path
        self.log = self.root / "gpu-log.jsonl"
        self.guard_log = self.root / "guard-log.jsonl"
        self.dbus_log = self.root / "dbus-log.jsonl"
        runtime = {
            "virtualMonitor": "1280x720",
            "startupTimeoutSeconds": 5,
            "allowedVendorPatterns": ["Test GPU Vendor"],
            "allowedRendererPatterns": ["Test GPU Renderer"],
        }
        paths = {
            "dbusRunSession": self.tools["dbus"],
            "dbusDaemon": self.tools["dbus"],
            "mutter": self.tools["mutter"],
            "python": Path(sys.executable).resolve(),
            "xwayland": self.tools["Xwayland"],
            "glxinfo": self.tools["glxinfo"],
            "xrandr": self.tools["xrandr"],
        }
        for field, path in paths.items():
            runtime[field + "Executable"] = str(path)
            runtime[field + "Sha256"] = self.sha(path)
        self.target = {"isolatedX11": True, "gpuHeadlessRuntime": runtime}
        self.base = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "FAKE_GPU_LOG": str(self.log),
            "FAKE_GUARD_LOG": str(self.guard_log),
            "FAKE_DBUS_LOG": str(self.dbus_log),
            "FAKE_XWAYLAND": str(self.tools["Xwayland"]),
            "WAYLAND_DISPLAY": "wayland-visible", "WAYLAND_SOCKET": "visible",
            "DISPLAY": ":0", "XAUTHORITY": "/visible/auth",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/visible/bus",
            "DBUS_SESSION_BUS_PID": "999",
            "DBUS_SESSION_BUS_WINDOWID": "1234",
            "DBUS_STARTER_ADDRESS": "unix:path=/visible/starter",
            "AT_SPI_BUS_ADDRESS": "unix:path=/visible/atspi",
            "XDG_SESSION_TYPE": "wayland", "GTK_USE_PORTAL": "1",
            "QT_NO_XDG_DESKTOP_PORTAL": "0",
            "MUTTER_DEBUG_DUMMY_MODE_SPECS": "8192x4096",
            "MUTTER_DEBUG_FAKE": "hostile",
            "LD_LIBRARY_PATH": "/hostile/libraries",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "MESA_LOADER_DRIVER_OVERRIDE": "llvmpipe",
        }
        self.original_session_guard = GPU.SESSION_GUARD
        GPU.SESSION_GUARD = self.tools["session-guard"]
        self.lifecycle = GPU.GpuHeadlessLifecycle(self.target, self.state)

    def tearDown(self) -> None:
        try:
            self.lifecycle.cleanup()
        except RuntimeError:
            state = self.lifecycle._read_state()
            if state and state.get("lifecycleRoot"):
                group = state["lifecycleRoot"]["processGroup"]
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.lifecycle._reap_if_child(state["lifecycleRoot"]["pid"])
        GPU.SESSION_GUARD = self.original_session_guard
        self.temporary.cleanup()

    @staticmethod
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def assert_private(self, path: Path, mode: int) -> None:
        self.assertEqual(mode, path.stat().st_mode & 0o777)
        self.assertEqual(os.getuid(), path.stat().st_uid)

    def test_full_gpu_lifecycle_is_private_owned_reusable_and_idempotent(self) -> None:
        environment = self.lifecycle.ensure_started(self.base)
        self.assertEqual(":1777", environment["DISPLAY"])
        self.assertEqual("xcb", environment["QT_QPA_PLATFORM"])
        self.assertEqual("x11", environment["XDG_SESSION_TYPE"])
        for forbidden in ("WAYLAND_DISPLAY", "WAYLAND_SOCKET",
                          "DBUS_SESSION_BUS_ADDRESS", "DBUS_STARTER_ADDRESS",
                          "AT_SPI_BUS_ADDRESS"):
            self.assertNotIn(forbidden, environment)
        self.assertEqual("0", environment["GTK_USE_PORTAL"])
        self.assertEqual("1", environment["QT_NO_XDG_DESKTOP_PORTAL"])
        self.assertEqual("local", environment["GIO_USE_VFS"])
        self.assertEqual("none", environment["GTK_A11Y"])
        state = self.lifecycle._read_state()
        self.assertEqual("ready", state["phase"])
        self.assertEqual("Test GPU Vendor", state["renderer"]["vendor"])
        group = state["lifecycleRoot"]["pid"]
        self.assertEqual(group, state["lifecycleRoot"]["processGroup"])
        for name in ("sessionGuard", "mutter", "sentinel", "xwayland"):
            self.assertEqual(group, state[name]["processGroup"])
            self.assertTrue(self.lifecycle._component_owned(state[name]))
        self.assertEqual(group, state["sessionGuard"]["parentPid"])
        self.assertEqual(state["sessionGuard"]["pid"], state["mutter"]["parentPid"])
        for path in (self.lifecycle.state_path, self.lifecycle.handoff_path,
                     self.lifecycle.glxinfo_path, self.lifecycle.xrandr_path):
            self.assert_private(path, 0o600)
        self.assert_private(self.lifecycle.runtime_directory, 0o700)
        invocation = json.loads(self.log.read_text(encoding="utf-8").splitlines()[0])
        dbus_invocation = json.loads(
            self.dbus_log.read_text(encoding="utf-8").splitlines()[0])
        self.assertIn(
            f"--dbus-daemon={self.lifecycle.runtime['dbusDaemon']['path']}",
            dbus_invocation)
        guard_invocation = json.loads(
            self.guard_log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(str(self.tools["mutter"]),
                         guard_invocation[guard_invocation.index("--mutter") + 1])
        self.assertIn("--headless", invocation["arguments"])
        self.assertIn("--virtual-monitor=1280x720", invocation["arguments"])
        self.assertNotIn("--display-server", invocation["arguments"])
        child = invocation["environment"]
        self.assertIsNone(child["DISPLAY"])
        self.assertIsNone(child["WAYLAND_DISPLAY"])
        self.assertNotEqual("unix:path=/visible/bus", child["DBUS_SESSION_BUS_ADDRESS"])
        self.assertTrue(child["DBUS_SESSION_BUS_ADDRESS"].startswith(
            "unix:path=" + str(self.lifecycle.runtime_directory)))
        self.assertEqual("local", child["GIO_USE_VFS"])
        self.assertEqual("none", child["GTK_A11Y"])
        for protected in ("LD_LIBRARY_PATH", "LIBGL_ALWAYS_SOFTWARE",
                          "MESA_LOADER_DRIVER_OVERRIDE", "MUTTER_DEBUG_FAKE",
                          "MUTTER_DEBUG_DUMMY_MODE_SPECS"):
            self.assertIsNone(child[protected])
        reused = self.lifecycle.ensure_started(self.base)
        self.assertEqual(environment["DISPLAY"], reused["DISPLAY"])
        self.assertEqual(1, len(self.log.read_text(encoding="utf-8").splitlines()))
        self.assertTrue(self.lifecycle.cleanup())
        self.assertFalse(self.lifecycle.cleanup())

    def test_wayland_socket_fits_the_default_state_root_and_rejects_long_roots(self) -> None:
        default_state = (Path("/tmp/overte-device-adapter-state-1000")
                         / ("a" * 24) / "gpu-headless")
        socket_path = default_state / "runtime" / self.lifecycle.socket_name
        self.assertLess(len(os.fsencode(str(socket_path))), GPU.SUN_PATH_BYTES)
        self.assertEqual("overte-e2e", self.lifecycle.socket_name)

        long_state = self.root / ("long-state-" + "x" * 80)
        with self.assertRaisesRegex(RuntimeError, "socket path exceeds Linux limit"):
            GPU.GpuHeadlessLifecycle(self.target, long_state)

    def test_renderer_gate_rejects_all_fail_closed_classes(self) -> None:
        cases = (
            ("indirect", "not direct-rendered"),
            ("software", "software denylist"),
            ("vendor", "vendor is not allowlisted"),
            ("renderer", "renderer is not allowlisted"),
        )
        for mode, message in cases:
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(RuntimeError, message):
                    self.lifecycle.ensure_started({**self.base, "FAKE_GLX_MODE": mode})
                self.assertFalse(self.lifecycle.state_path.exists())
                self.assertFalse(self.lifecycle.runtime_directory.exists())

    def test_monitor_gate_rejects_wrong_size_and_multiple_outputs(self) -> None:
        for mode in ("wrong", "multi"):
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    RuntimeError, "configured monitor|root extent"):
                self.lifecycle.ensure_started({**self.base, "FAKE_XRANDR_MODE": mode})
            self.assertFalse(self.lifecycle.state_path.exists())

    def test_ambiguous_xwayland_is_rejected_and_cleaned(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "ownership is ambiguous"):
            self.lifecycle.ensure_started({**self.base, "FAKE_EXTRA_XWAYLAND": "1"})
        self.assertFalse(self.lifecycle.state_path.exists())
        self.assertFalse(self.lifecycle.runtime_directory.exists())

    def test_portal_input_emulation_xwayland_is_rejected_and_cleaned(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "portal input emulation"):
            self.lifecycle.ensure_started({**self.base, "FAKE_XWAYLAND_EI_PORTAL": "1"})
        self.assertFalse(self.lifecycle.state_path.exists())
        self.assertFalse(self.lifecycle.runtime_directory.exists())

    def test_cleanup_refuses_tampered_live_xwayland_identity(self) -> None:
        self.lifecycle.ensure_started(self.base)
        state = self.lifecycle._read_state()
        original = state["xwayland"]["processToken"]
        state["xwayland"]["processToken"] = str(int(original) + 1)
        self.lifecycle._save_state(state)
        with self.assertRaisesRegex(RuntimeError, "mismatched identity"):
            self.lifecycle.cleanup()
        state["xwayland"]["processToken"] = original
        self.lifecycle._save_state(state)
        self.assertTrue(self.lifecycle.cleanup())

    def test_dead_owned_group_is_recovered_and_restarted(self) -> None:
        self.lifecycle.ensure_started(self.base)
        state = self.lifecycle._read_state()
        os.killpg(state["lifecycleRoot"]["processGroup"], signal.SIGKILL)
        deadline = time.monotonic() + 5
        while (GPU._process_details(state["lifecycleRoot"]["pid"]) is not None
               and time.monotonic() < deadline):
            self.lifecycle._reap_if_child(state["lifecycleRoot"]["pid"])
            time.sleep(0.02)
        self.lifecycle._reap_if_child(state["lifecycleRoot"]["pid"])
        environment = self.lifecycle.ensure_started(self.base)
        self.assertEqual(":1777", environment["DISPLAY"])
        self.assertEqual(2, len(self.log.read_text(encoding="utf-8").splitlines()))

    def test_ready_state_transport_or_proof_tampering_forces_owned_restart(self) -> None:
        self.lifecycle.ensure_started(self.base)
        state = self.lifecycle._read_state()
        state["display"] = ":99999"
        self.lifecycle._save_state(state)
        environment = self.lifecycle.ensure_started(self.base)
        self.assertEqual(":1777", environment["DISPLAY"])
        self.assertEqual(2, len(self.log.read_text(encoding="utf-8").splitlines()))
        self.lifecycle._write_private(
            self.lifecycle.glxinfo_path,
            "direct rendering: Yes\nOpenGL vendor string: Test GPU Vendor\n"
            "OpenGL renderer string: llvmpipe\n")
        environment = self.lifecycle.ensure_started(self.base)
        self.assertEqual(":1777", environment["DISPLAY"])
        self.assertEqual(3, len(self.log.read_text(encoding="utf-8").splitlines()))

    def test_ready_state_allows_only_the_lifecycle_root_to_be_reparented(self) -> None:
        self.lifecycle.ensure_started(self.base)
        state = self.lifecycle._read_state()
        original_details = GPU._process_details

        def with_parent(pid: int, component: str):
            details = original_details(pid)
            self.assertIsNotNone(details)
            token, group, parent, image, arguments = details
            if pid == state[component]["pid"]:
                parent = parent + 100000
            return token, group, parent, image, arguments

        with patch.object(
                GPU, "_process_details",
                side_effect=lambda pid: with_parent(pid, "lifecycleRoot")):
            self.assertTrue(self.lifecycle._state_ready(state))
        with patch.object(
                GPU, "_process_details",
                side_effect=lambda pid: with_parent(pid, "mutter")):
            self.assertFalse(self.lifecycle._state_ready(state))

    def test_configuration_rejects_old_fields_hashes_and_bad_allowlists(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "dbusRunSessionExecutable"):
            GPU.GpuHeadlessLifecycle._validate_runtime(
                {"display": ":93", "xvfbExecutable": "/bin/false"})
        broken = json.loads(json.dumps(self.target))
        broken["gpuHeadlessRuntime"]["mutterSha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            GPU.GpuHeadlessLifecycle(broken, self.root / "broken-state")
        broken = json.loads(json.dumps(self.target))
        broken["gpuHeadlessRuntime"]["allowedRendererPatterns"] = ["["]
        with self.assertRaisesRegex(RuntimeError, "invalid regex"):
            GPU.GpuHeadlessLifecycle(broken, self.root / "regex-state")

    def test_sentinel_never_replaces_a_preexisting_handoff(self) -> None:
        directory = self.root / "sentinel-state"
        directory.mkdir(mode=0o700)
        handoff = directory / "display-handoff.json"
        handoff.write_text("owner-data\n", encoding="utf-8")
        handoff.chmod(0o600)
        result = subprocess.run([
            sys.executable, str(GPU.SENTINEL), "--handoff", str(handoff),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
           env={**os.environ, "DISPLAY": ":88", "XAUTHORITY": str(directory / "auth"),
                "WAYLAND_DISPLAY": "wayland-test"}, timeout=5, check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("owner-data\n", handoff.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
