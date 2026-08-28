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
from unittest.mock import MagicMock, call, patch


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

    def controlled_adapter(self, platform: str) -> tuple[object, dict]:
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        target = next(item for item in payload["targets"] if item["platform"] == platform)
        target["probe"] = {"kind": "injected-test-script"}
        target["clientControl"] = {"kind": "probe-command-file"}
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, self.environment, clear=True):
            adapter = DESKTOP_MODULE.DesktopAdapter(platform)
        return adapter, adapter.target(f"{platform}-alias")

    @staticmethod
    def running_state() -> dict:
        return {"pid": 4242, "processToken": "token", "identity": "4242:token"}

    def test_new_capabilities_require_probe_command_control_on_every_desktop_variant(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        controlled = {"asset.load", "navigation.enter-domain", "sound.play"}
        for target in payload["targets"]:
            with self.subTest(platform=target["platform"], controlled=False):
                self.assertTrue(controlled.isdisjoint(
                    DESKTOP_MODULE.DesktopAdapter.capabilities(target)))
            target["probe"] = {"kind": "injected-test-script"}
            target["clientControl"] = {"kind": "probe-command-file"}
            with self.subTest(platform=target["platform"], controlled=True):
                self.assertTrue(controlled.issubset(
                    DESKTOP_MODULE.DesktopAdapter.capabilities(target)))

        linux = payload["targets"][0]
        linux["isolatedX11"] = True
        self.assertTrue(controlled.issubset(
            DESKTOP_MODULE.DesktopAdapter.capabilities(linux)))

    def test_contradictory_or_uncontrolled_probe_configuration_fails_closed(self):
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        linux = next(item for item in payload["targets"] if item["platform"] == "linux")
        linux["clientControl"] = {"kind": "probe-command-file"}
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "injected in-client probe"):
            DESKTOP_MODULE.DesktopAdapter("linux")

        linux["probe"] = {"kind": "injected-test-script"}
        linux["clientControl"] = {"kind": "portal"}
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "probe-command-file"):
            DESKTOP_MODULE.DesktopAdapter("linux")

    def test_navigation_and_asset_payloads_use_the_running_probe_process(self):
        adapter, target = self.controlled_adapter("macos")
        adapter.prepare_injected_probe("macos-alias")
        state = self.running_state()
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    DESKTOP_MODULE.subprocess, "Popen") as spawn:
            navigation = adapter.invoke(
                "macos-alias", "navigation.enter-domain",
                {"url": "hifi://127.0.0.1:40102/0,0,4/0,0,0,1"})
        spawn.assert_not_called()
        self.assertEqual({"requested": True}, navigation)
        command = json.loads(adapter.client_command_path("macos-alias").read_text())
        self.assertEqual("navigate", command["action"])
        self.assertEqual("hifi://127.0.0.1:40102/0,0,4/0,0,0,1", command["url"])

        values = {
            "assetId": "texture-rgb-3x1-v1",
            "url": "http://127.0.0.1:41000/assets/texture.png?requestId=exact",
            "entityName": "OVERTE_E2E_ASSET_LOAD",
        }
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True):
            asset = adapter.invoke("macos-alias", "asset.load", values)
        self.assertEqual({"requested": True}, asset)
        command = json.loads(adapter.client_command_path("macos-alias").read_text())
        self.assertEqual({"action": "asset-load", **values}, {
            key: command[key] for key in ("action", *values)})
        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        self.assertIn('Window.location = command.url', probe)
        self.assertIn('Entities.addEntity({', probe)
        self.assertIn('imageURL: command.url', probe)
        self.assertIn('overteE2EAssetId: command.assetId', probe)
        self.assertNotIn("Clipboard", probe)

    def test_controlled_launch_uses_private_probe_copy_in_the_authoritative_process(self):
        self.controlled_adapter("macos")
        (self.root / "interface-calls.log").unlink(missing_ok=True)
        result = self.call(
            "macos", "invoke", "--target", "macos-alias",
            "--operation", "app.launch")
        self.assertEqual(0, result.returncode, result.stdout)
        calls = [json.loads(line) for line in (self.root / "interface-calls.log").read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(1, len(calls))
        arguments = calls[0]
        script = Path(arguments[arguments.index("--testScript") + 1])
        results = Path(arguments[arguments.index("--testResultsLocation") + 1])
        self.assertEqual(results, script.parent)
        self.assertNotEqual(ROOT / "probe/overte_e2e_probe.js", script)
        self.assertEqual(0o600, script.stat().st_mode & 0o777)
        self.assertTrue((results / "desktop-command.json").is_file())
        process = self.call(
            "macos", "invoke", "--target", "macos-alias",
            "--operation", "app.process")
        self.assertEqual(0, process.returncode, process.stdout)
        self.assertTrue(json.loads(process.stdout)["running"])

    def test_sound_posts_exact_fixture_command_without_synthesizing_probe_state(self):
        adapter, _target = self.controlled_adapter("windows")
        adapter.prepare_injected_probe("windows-alias")
        state = self.running_state()
        values = {
            "schemaVersion": 1,
            "commandId": "sound-exact",
            "url": "http://127.0.0.1:41000/audio/overte-e2e-tone.wav?e2eCommand=sound-exact",
            "commandUrl": "http://127.0.0.1:41000/sound-command.json",
        }
        accepted = {
            "schemaVersion": 1, "commandId": "sound-exact", "action": "play",
            "soundUrl": values["url"],
        }
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps(accepted).encode("utf-8")
        response.__enter__.return_value = response
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    DESKTOP_MODULE, "urlopen", return_value=response) as opened:
            result = adapter.invoke("windows-alias", "sound.play", values)
        self.assertEqual({"requested": True, "commandId": "sound-exact"}, result)
        request = opened.call_args.args[0]
        self.assertEqual(values["commandUrl"], request.full_url)
        self.assertEqual(accepted, json.loads(request.data))
        command = json.loads(adapter.client_command_path("windows-alias").read_text())
        self.assertEqual("sound-channel", command["action"])
        self.assertEqual(values["commandUrl"], command["url"])
        self.assertNotIn("resourceReady", command)
        self.assertNotIn("injectorCreated", command)

    def test_control_operations_reject_missing_probe_invalid_arguments_and_process_switch(self):
        adapter, _target = self.controlled_adapter("macos")
        adapter.prepare_injected_probe("macos-alias")
        state = self.running_state()
        invalid = (
            ("navigation.enter-domain", {"url": "https://fixture.invalid"}),
            ("asset.load", {"assetId": "BAD", "url": "http://fixture/a.png",
                            "entityName": "OVERTE_E2E_ASSET_LOAD"}),
            ("sound.play", {"schemaVersion": 1, "commandId": "id",
                            "url": "file:///tone.wav", "commandUrl": "http://fixture/c"}),
        )
        for operation, arguments in invalid:
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                adapter.invoke("macos-alias", operation, arguments)

        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", side_effect=[True, True, False]), self.assertRaisesRegex(
                    RuntimeError, "process changed"):
            adapter.invoke("macos-alias", "navigation.enter-domain", {
                "url": "hifi://127.0.0.1:40102/",
            })

        payload = json.loads(self.config.read_text(encoding="utf-8"))
        macos = next(item for item in payload["targets"] if item["platform"] == "macos")
        macos.pop("clientControl")
        macos["probe"] = {"kind": "host-file", "path": str(self.probe)}
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, self.environment, clear=True):
            uncontrolled = DESKTOP_MODULE.DesktopAdapter("macos")
        with patch.object(uncontrolled, "read_state", return_value=state), patch.object(
                uncontrolled, "state_alive", return_value=True), self.assertRaisesRegex(
                    RuntimeError, "controlled in-client probe"):
            uncontrolled.invoke("macos-alias", "navigation.enter-domain", {
                "url": "hifi://127.0.0.1:40102/",
            })

    def test_cleanup_removes_private_probe_control_artifacts(self):
        adapter, _target = self.controlled_adapter("macos")
        script = adapter.prepare_injected_probe("macos-alias")
        command = adapter.client_command_path("macos-alias")
        self.assertEqual(0o600, script.stat().st_mode & 0o777)
        self.assertEqual(0o600, command.stat().st_mode & 0o777)
        with patch.object(adapter, "read_state", return_value=None):
            self.assertEqual({"cleaned": True}, adapter.cleanup("macos-alias"))
        self.assertFalse(script.exists())
        self.assertFalse(command.exists())

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
