#!/usr/bin/env python3
"""Device-free process and native-input tests for every desktop manifest."""

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
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters/desktop_oculix/adapter.py"
VERIFIER = ROOT / "verify_adapter.py"
SPEC = importlib.util.spec_from_file_location("desktop_oculix_adapter", ADAPTER)
DESKTOP_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DESKTOP_MODULE)


FAKE_INTERFACE = r'''#!/usr/bin/env python3
import json, os, signal, sys, time
with open(os.environ["MOCK_INTERFACE_LOG"], "a", encoding="utf-8") as out:
    out.write(json.dumps(sys.argv[1:]) + "\n")
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True: time.sleep(0.2)
'''

FAKE_JAVA = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
action=sys.argv[-2]
values=json.loads(sys.argv[-1])
with open(os.environ["MOCK_OCULIX_LOG"], "a", encoding="utf-8") as out:
    out.write(action + "\n")
with open(os.environ["MOCK_OCULIX_ENV_LOG"], "a", encoding="utf-8") as out:
    out.write(json.dumps({key: os.environ.get(key) for key in (
        "DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET",
        "XDG_SESSION_TYPE", "GDK_BACKEND", "DBUS_SESSION_BUS_ADDRESS")}) + "\n")
if action == "screenshot":
    path=pathlib.Path(values["artifactDirectory"]) / values["filename"]
    path.write_bytes(b"mock-desktop-png")
'''

FAKE_XDOTOOL = r'''#!/usr/bin/env python3
import json, os, sys
arguments=sys.argv[1:]
with open(os.environ["MOCK_XDOTOOL_LOG"], "a", encoding="utf-8") as out:
    out.write(json.dumps(arguments) + "\n")
if arguments and arguments[0] == "search":
    print("1001")
elif arguments and arguments[0] == "getwindowgeometry":
    print("WINDOW=1001\nX=10\nY=20\nWIDTH=1280\nHEIGHT=720\nSCREEN=0")
'''

FAKE_SCREENSHOT = r'''#!/usr/bin/env python3
import pathlib, sys
pathlib.Path(sys.argv[-1]).write_bytes(b"mock-desktop-png")
'''

FAKE_LIBEI_DAEMON = r'''#!/usr/bin/env python3
import json, os, pathlib, socket, sys, time
with open(os.environ["MOCK_LIBEI_ARGV_LOG"], "a", encoding="utf-8") as output:
    output.write(json.dumps(sys.argv[1:]) + "\n")
def value(name):
    index=sys.argv.index(name)
    return sys.argv[index + 1]
target=value("--target")
runtime=pathlib.Path(value("--runtime-root")) / target
runtime.mkdir(parents=True, mode=0o700, exist_ok=True)
os.chmod(runtime, 0o700)
endpoint=runtime / "input.sock"
endpoint.unlink(missing_ok=True)
listener=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
listener.bind(str(endpoint))
os.chmod(endpoint, 0o600)
listener.listen(4)
print(f"READY socket={endpoint}", flush=True)
running=True
while running:
    connection, _ = listener.accept()
    with connection:
        request=b""
        while b"\n" not in request:
            block=connection.recv(512)
            if not block: break
            request += block
        text=request.decode("ascii").strip()
        with open(os.environ["MOCK_LIBEI_LOG"], "a", encoding="utf-8") as output:
            output.write(text + "\n")
        if text == "status":
            response=b"OK ready=1 pointer=1 button=1 keyboard=1\n"
        elif text == "shutdown":
            response=b"OK\n"; running=False
        else:
            if text == "key 15 up" and os.environ.get("MOCK_PROBE_PATH"):
                probe_path=pathlib.Path(os.environ["MOCK_PROBE_PATH"])
                probe=json.loads(probe_path.read_text(encoding="utf-8"))
                probe["tablet"]["open"] = not probe["tablet"]["open"]
                probe["sampleEpochMs"] = int(time.time() * 1000)
                probe_path.write_text(json.dumps(probe), encoding="utf-8")
            response=b"OK\n"
        connection.sendall(response)
listener.close()
endpoint.unlink(missing_ok=True)
'''


class DesktopAdapterTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX process groups are unavailable")
    def test_posix_cleanup_detects_child_after_group_leader_exits(self):
        parent = subprocess.Popen([
            sys.executable, "-c",
            "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])",
        ], start_new_session=True)
        parent.wait(timeout=5)
        state = {"pid": parent.pid, "processToken": "expired"}
        try:
            self.assertFalse(DESKTOP_MODULE.DesktopAdapter.state_alive(state))
            self.assertTrue(DESKTOP_MODULE.DesktopAdapter.process_tree_alive(state))
            DESKTOP_MODULE.DesktopAdapter.terminate_process_tree(parent.pid, force=True)
            deadline = time.monotonic() + 5
            while (DESKTOP_MODULE.DesktopAdapter.process_tree_alive(state)
                   and time.monotonic() < deadline):
                time.sleep(0.05)
            self.assertFalse(DESKTOP_MODULE.DesktopAdapter.process_tree_alive(state))
        finally:
            try:
                os.killpg(parent.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_windows_cleanup_uses_normal_then_forced_process_tree_kill(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(DESKTOP_MODULE.os, "name", "nt"), patch.object(
                DESKTOP_MODULE.subprocess, "run", return_value=completed) as run:
            DESKTOP_MODULE.DesktopAdapter.terminate_process_tree(42, force=False)
            DESKTOP_MODULE.DesktopAdapter.terminate_process_tree(42, force=True)
        self.assertEqual(
            [call(["taskkill", "/PID", "42", "/T"],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  timeout=15, check=False),
             call(["taskkill", "/PID", "42", "/T", "/F"],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  timeout=15, check=False)],
            run.call_args_list,
        )

    def test_macos_process_token_ignores_dynamic_scheduler_state(self):
        responses = [
            subprocess.CompletedProcess([], 0, "R Tue Aug 25 10:00:00 2026\n", ""),
            subprocess.CompletedProcess([], 0, "S Tue Aug 25 10:00:00 2026\n", ""),
            subprocess.CompletedProcess([], 0, "Z Tue Aug 25 10:00:00 2026\n", ""),
            subprocess.CompletedProcess([], 0, "S Tue Aug 25 10:00:01 2026\n", ""),
        ]
        with patch.object(DESKTOP_MODULE.sys, "platform", "darwin"), patch.object(
                DESKTOP_MODULE.subprocess, "run", side_effect=responses):
            first = DESKTOP_MODULE.DesktopAdapter.process_token(42)
            second = DESKTOP_MODULE.DesktopAdapter.process_token(42)
            zombie = DESKTOP_MODULE.DesktopAdapter.process_token(42)
            reused = DESKTOP_MODULE.DesktopAdapter.process_token(42)
        self.assertEqual(first, second)
        self.assertIsNone(zombie)
        self.assertNotEqual(first, reused)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-adapter-test-")
        self.root = Path(self.temporary.name)
        self.interface = self.root / "fake_interface.py"
        self.java = self.root / "fake_java.py"
        self.xdotool = self.root / "xdotool"
        self.screenshot = self.root / "import"
        self.libei_daemon = self.root / "wayland-libei-daemon"
        self.jar = self.root / "oculix.jar"
        self.interface.write_text(FAKE_INTERFACE, encoding="utf-8")
        self.java.write_text(FAKE_JAVA, encoding="utf-8")
        self.interface.chmod(0o700)
        self.java.chmod(0o700)
        self.xdotool.write_text(FAKE_XDOTOOL, encoding="utf-8")
        self.screenshot.write_text(FAKE_SCREENSHOT, encoding="utf-8")
        self.libei_daemon.write_text(FAKE_LIBEI_DAEMON, encoding="utf-8")
        self.xdotool.chmod(0o700)
        self.screenshot.chmod(0o700)
        self.libei_daemon.chmod(0o700)
        self.jar.write_bytes(b"mock jar")
        self.probe = self.root / "probe.json"
        self.write_probe()
        targets = []
        for platform in ("linux", "macos", "windows"):
            target = {
                "selector": f"{platform}-alias", "displayName": platform,
                "platform": platform, "physical": False, "enabled": True,
                "executable": sys.executable, "arguments": [str(self.interface)],
                "workingDirectory": str(self.root), "windowTitle": "Overte",
                "environment": {},
                "oculixJar": str(self.jar), "javaExecutable": sys.executable,
                "javaArguments": [str(self.java)],
                "oculixSha256": hashlib.sha256(b"mock jar").hexdigest(),
                "xdotoolExecutable": str(self.xdotool),
                "xdotoolSha256": hashlib.sha256(
                    self.xdotool.read_bytes()).hexdigest(),
                "screenshotExecutable": str(self.screenshot),
                "screenshotSha256": hashlib.sha256(
                    self.screenshot.read_bytes()).hexdigest(),
                "screenshotArguments": [],
                "probe": {"kind": "host-file", "path": str(self.probe)},
            }
            if platform == "linux":
                target.update({
                    "inputDriver": "wayland-libei",
                    "waylandInputTarget": "test-visible",
                    "waylandInputDaemonExecutable": str(self.libei_daemon),
                    "waylandInputDaemonSha256": hashlib.sha256(
                        self.libei_daemon.read_bytes()).hexdigest(),
                    "waylandInputStateRoot": str(self.root / "wayland-state"),
                    "waylandInputRuntimeRoot": str(self.root / "wayland-runtime"),
                    "waylandInputPortalTimeoutSeconds": 10,
                    "desktopSize": {"width": 1280, "height": 720},
                })
            targets.append(target)
        self.config = self.root / "targets.json"
        self.config.write_text(json.dumps({"schemaVersion": 1, "targets": targets}),
                               encoding="utf-8")
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.environment = os.environ.copy()
        self.environment.update({
            "OVERTE_DESKTOP_TARGETS": str(self.config),
            "OVERTE_DEVICE_STATE_ROOT": str(self.root / "state"),
            "OVERTE_DEVICE_ARTIFACT_DIR": str(self.artifacts),
            "OVERTE_E2E_SCENE_URL": "http://fixture/scene.json",
            "MOCK_INTERFACE_LOG": str(self.root / "interface-calls.log"),
            "MOCK_OCULIX_LOG": str(self.root / "oculix-calls.log"),
            "MOCK_OCULIX_ENV_LOG": str(self.root / "oculix-environment.log"),
            "MOCK_XDOTOOL_LOG": str(self.root / "xdotool-calls.log"),
            "MOCK_LIBEI_LOG": str(self.root / "libei-calls.log"),
            "MOCK_LIBEI_ARGV_LOG": str(self.root / "libei-argv.log"),
            "MOCK_PROBE_PATH": str(self.probe),
            "XDG_SESSION_TYPE": "x11",
            "DISPLAY": ":99",
            "PATH": str(self.root) + os.pathsep + self.environment.get("PATH", ""),
        })

    def tearDown(self):
        for platform in ("linux", "macos", "windows"):
            self.call(platform, "cleanup", "--target", f"{platform}-alias")
        self.temporary.cleanup()

    def write_probe(self):
        self.probe.write_text(json.dumps({
            "schemaVersion": 1, "sampleEpochMs": int(time.time() * 1000),
            "build": {"platform": "Mock", "version": "desktop-contract",
                      "date": "1970-01-01"},
            "application": {"running": True, "foreground": True},
            "scene": {"url": "http://fixture/scene.json", "ready": True, "entityCount": 4},
            "avatar": {"position": {"x": 0, "y": 1, "z": 4}},
            "view": {"orientation": {"x": 0, "y": 0, "z": 0}},
            "tablet": {"open": False},
        }), encoding="utf-8")

    def call(self, platform: str, action: str, *extra: str) -> subprocess.CompletedProcess:
        self.write_probe()
        return subprocess.run([
            sys.executable, str(ADAPTER), "--platform", platform, action, *extra,
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=self.environment, check=False)

    def test_all_desktop_manifests_satisfy_protocol(self):
        for platform in ("linux", "macos", "windows"):
            result = subprocess.run([
                sys.executable, str(VERIFIER), "--adapter-manifest",
                str(ROOT / f"adapters/desktop_oculix/{platform}.json"),
                "--check-cleanup",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=self.environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            self.assertIn("for 1 target(s)", result.stdout)

    def test_disabled_linux_targets_do_not_require_an_x11_session(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        for target in payload["targets"]:
            target["enabled"] = False
            target["physical"] = True
        linux = next(target for target in payload["targets"]
                     if target["platform"] == "linux")
        linux.update({
            "isolatedX11": True,
            "xwayland": False,
            "inputDriver": "xdotool",
            "environment": {"QT_QPA_PLATFORM": "xcb"},
            # A disabled lab slot is allowed to remain unprovisioned.
            "gpuHeadlessRuntime": {},
        })
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, {
                "OVERTE_DESKTOP_TARGETS": str(self.config),
                "XDG_SESSION_TYPE": "wayland",
                "WAYLAND_DISPLAY": "wayland-0",
        }, clear=True):
            adapter = DESKTOP_MODULE.DesktopAdapter("linux")
            self.assertEqual([], adapter.discover())

    def test_linux_physical_target_can_opt_into_xcb_on_xwayland(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        linux = next(target for target in payload["targets"] if target["platform"] == "linux")
        linux["physical"] = True
        linux["xwayland"] = True
        linux["environment"] = {"QT_QPA_PLATFORM": "xcb"}
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, {
                "OVERTE_DESKTOP_TARGETS": str(self.config),
                "XDG_SESSION_TYPE": "wayland", "DISPLAY": ":99",
                "PATH": str(self.root),
        }, clear=True):
            adapter = DESKTOP_MODULE.DesktopAdapter("linux")
            self.assertEqual("linux-alias", adapter.discover()[0]["selector"])

        linux["environment"] = {}
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, {
                "OVERTE_DESKTOP_TARGETS": str(self.config),
                "XDG_SESSION_TYPE": "wayland", "DISPLAY": ":99",
                "PATH": str(self.root),
        }, clear=True), self.assertRaisesRegex(RuntimeError, "xcb"):
            DESKTOP_MODULE.DesktopAdapter("linux").discover()

    def test_isolated_x11_visual_driver_cannot_reach_wayland_or_session_portal(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        linux = next(target for target in payload["targets"] if target["platform"] == "linux")
        linux["physical"] = True
        linux["isolatedX11"] = True
        linux["inputDriver"] = "xdotool"
        linux["xwayland"] = False
        linux["environment"] = {"QT_QPA_PLATFORM": "xcb"}
        tool_hash = hashlib.sha256(self.xdotool.read_bytes()).hexdigest()
        linux["gpuHeadlessRuntime"] = {
            "virtualMonitor": "1280x720",
            "allowedVendorPatterns": ["Test Vendor"],
            "allowedRendererPatterns": ["Test Renderer"],
            **{
                field + "Executable": str(self.xdotool)
                for field in ("dbusRunSession", "dbusDaemon", "mutter", "python",
                              "xwayland", "glxinfo", "xrandr")
            },
            **{
                field + "Sha256": tool_hash
                for field in ("dbusRunSession", "dbusDaemon", "mutter", "python",
                              "xwayland", "glxinfo", "xrandr")
            },
        }
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, {
                **self.environment, "WAYLAND_DISPLAY": "wayland-0",
                "WAYLAND_SOCKET": "wayland-0", "XDG_SESSION_TYPE": "wayland",
                "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        }, clear=True):
            adapter = DESKTOP_MODULE.DesktopAdapter("linux")
            self.assertEqual("linux-alias", adapter.discover()[0]["selector"])
            child = adapter.target_environment(linux, visual_driver=True)
        self.assertEqual("x11", child["XDG_SESSION_TYPE"])
        self.assertEqual("x11", child["GDK_BACKEND"])
        self.assertNotIn("WAYLAND_DISPLAY", child)
        self.assertNotIn("WAYLAND_SOCKET", child)
        self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", child)

    def test_visible_linux_operations_share_one_persistent_libei_daemon(self):
        (self.root / "oculix-calls.log").unlink(missing_ok=True)
        (self.root / "interface-calls.log").unlink(missing_ok=True)
        target = ("--target", "linux-alias")
        launched = self.call("linux", "invoke", *target, "--operation", "app.launch")
        self.assertEqual(0, launched.returncode, launched.stdout)
        for operation, values in (
            ("app.process", {}), ("app.foreground", {}),
            ("scene.load", {"url": "http://fixture/scene.json"}),
            ("input.look", {"horizontal": 0.25}),
            ("input.move", {"direction": "forward", "durationSeconds": 0.1}),
            ("tablet.open", {}), ("tablet.close", {}),
        ):
            result = self.call("linux", "invoke", *target, "--operation", operation,
                               "--arguments", json.dumps(values))
            self.assertEqual(0, result.returncode, f"{operation}: {result.stdout}")
        actions_path = self.root / "oculix-calls.log"
        self.assertFalse(actions_path.exists(), "Linux must not invoke OculiX")
        self.assertFalse((self.root / "xdotool-calls.log").exists(),
                         "visible Wayland must never invoke xdotool")
        libei_calls = (self.root / "libei-calls.log").read_text(
            encoding="utf-8").splitlines()
        self.assertIn("button 273 down", libei_calls)
        self.assertIn("key 17 down", libei_calls)
        self.assertIn("key 15 down", libei_calls)
        self.assertIn("key 15 up", libei_calls)
        self.assertGreaterEqual(libei_calls.count(
            "status"), 4, "all actions must reuse the ready daemon")
        daemon_invocations = [json.loads(line) for line in
                              (self.root / "libei-argv.log").read_text(
                                  encoding="utf-8").splitlines()]
        self.assertEqual(1, len(daemon_invocations))
        self.assertNotIn("--authorize", daemon_invocations[0],
                         "normal test launch must never request a new grant")
        interface_calls = [json.loads(line) for line in
                           (self.root / "interface-calls.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(interface_calls), interface_calls)
        self.assertEqual(["--no-launcher", "--no-updater", "--no-login-suggestion",
                          "--display=Desktop", "--url", "http://fixture/scene.json"],
                         interface_calls[0])
        cleaned = self.call("linux", "cleanup", *target)
        self.assertEqual(0, cleaned.returncode, cleaned.stdout)
        self.assertEqual(1, (self.root / "libei-calls.log").read_text(
            encoding="utf-8").splitlines().count("shutdown"))

    def test_wayland_authorization_is_a_separate_explicit_action(self):
        target = ("--target", "linux-alias")
        result = self.call("linux", "authorize-input", *target)
        self.assertEqual(0, result.returncode, result.stdout)
        arguments = json.loads((self.root / "libei-argv.log").read_text(
            encoding="utf-8").splitlines()[0])
        self.assertIn("--authorize", arguments)
        cleaned = self.call("linux", "cleanup", *target)
        self.assertEqual(0, cleaned.returncode, cleaned.stdout)

    def test_visible_wayland_does_not_advertise_host_screenshot(self):
        with patch.dict(os.environ, self.environment, clear=True):
            adapter = DESKTOP_MODULE.DesktopAdapter("linux")
            target = adapter.target("linux-alias")
            self.assertNotIn("artifact.screenshot", adapter.capabilities(target))

    def test_direct_xdotool_on_visible_wayland_is_rejected(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        linux = next(target for target in payload["targets"] if target["platform"] == "linux")
        linux["inputDriver"] = "xdotool"
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "wayland-libei"):
            DESKTOP_MODULE.DesktopAdapter("linux")


if __name__ == "__main__":
    unittest.main()
