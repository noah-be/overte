#!/usr/bin/env python3
"""Device-free W3C protocol tests for the Android/iOS Appium adapter."""

from __future__ import annotations

import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "appium" / "adapter.py"
VERIFIER = ROOT / "verify_adapter.py"


MOCK_ADB = r'''#!/usr/bin/env python3
import json,os,shlex,sys
a=sys.argv[1:]
target = a[1] if len(a) > 2 and a[0] == "-s" else None
cmd = a[2:] if target else a
if cmd == ["get-state"]:
    print("device")
elif cmd == ["shell", "getprop", "ro.kernel.qemu"]:
    print("0")
elif cmd == ["shell", "run-as", "org.overte.phone", "cat",
             "files/overte-e2e/overte-probe.json"]:
    with open(os.environ["OVERTE_MOCK_ANDROID_PROBE"], encoding="utf-8") as source:
        print(source.read(), end="")
elif cmd == ["shell", "run-as", "org.overte.phone", "cat",
             "files/overte-e2e/e2e-client-command.json"]:
    path = os.environ["OVERTE_MOCK_ANDROID_COMMAND_FILE"]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as source:
            print(source.read(), end="")
elif cmd == ["shell", "pidof", "-s", "org.overte.phone"]:
    print("2468")
elif cmd == ["shell", "cat", "/proc/2468/stat"]:
    changed = os.path.exists(os.environ["OVERTE_MOCK_ANDROID_RESTART_MARKER"])
    print("2468 (overte) S " + " ".join(["0"] * 18) + (" 101" if changed else " 100"))
elif (len(cmd) == 2 and cmd[0] == "shell"
      and shlex.split(cmd[1])[:3] == ["run-as", "org.overte.phone", "sh"]
      and shlex.split(cmd[1])[-1] == "files/overte-e2e/e2e-client-command.json"):
    remote_arguments = shlex.split(cmd[1])
    if remote_arguments[3] != "-c" or remote_arguments[5] != "overte-e2e-write":
        raise SystemExit(8)
    content = sys.stdin.read()
    with open(os.environ["OVERTE_MOCK_ANDROID_COMMAND_FILE"], "w", encoding="utf-8") as sink:
        sink.write(content)
    with open(os.environ["OVERTE_MOCK_ANDROID_COMMAND_LOG"], "a", encoding="utf-8") as sink:
        sink.write(json.dumps(json.loads(content), sort_keys=True) + "\n")
    if os.environ.get("OVERTE_MOCK_ANDROID_RESTART_AFTER_WRITE") == "1":
        open(os.environ["OVERTE_MOCK_ANDROID_RESTART_MARKER"], "w").close()
'''


class AppiumHandler(BaseHTTPRequestHandler):
    calls: list[tuple[str, str]] = []
    executions: list[tuple[str, dict]] = []
    action_payloads: list[dict] = []
    probe_content = b""
    test_build_attested = True
    app_state = 1
    sound_commands: list[dict] = []
    reject_sound = False
    reject_webdriver = False
    source_content = '<hierarchy><node content-desc="OverteTablet"/></hierarchy>'
    element_requests: list[dict] = []
    restart_on_element_click = False
    restart_marker: Path | None = None

    def response(self, value: object) -> None:
        content = json.dumps({"value": value}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        self.calls.append(("GET", self.path))
        if self.path.endswith("/window/rect"):
            self.response({"x": 0, "y": 0, "width": 1000, "height": 500})
        elif self.path.endswith("/source"):
            self.response(self.source_content)
        elif self.path.endswith("/screenshot"):
            self.response(base64.b64encode(b"mock-png").decode())
        else:
            self.response({"sessionId": "session-private", "capabilities": {}})

    def do_POST(self) -> None:  # noqa: N802
        self.calls.append(("POST", self.path))
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/sound-command.json":
            if self.reject_sound:
                self.send_error(503)
                return
            self.sound_commands.append(payload)
            content = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/session":
            self.response({"sessionId": "session-private", "capabilities": {}})
        elif self.path.endswith("/execute/sync") and self.reject_webdriver:
            self.response({"error": "unknown error"})
        elif self.path.endswith("/execute/sync") and payload.get("script") == "mobile: queryAppState":
            arguments = payload.get("args", [{}])[0]
            self.response(4 if "appId" in arguments else self.app_state)
        elif self.path.endswith("/execute/sync"):
            script = payload.get("script")
            arguments = payload.get("args", [{}])[0]
            self.executions.append((script, arguments))
            if script == "mobile: deviceInfo":
                self.response({"isSimulator": False})
            elif script == "mobile: listApps":
                attributes = {
                    "CFBundleIdentifier": "org.overte.interface.dev",
                    "UIFileSharingEnabled": True,
                    "OverteE2ETestBuildContractVersion": 1,
                }
                if not self.test_build_attested:
                    attributes.pop("OverteE2ETestBuildContractVersion")
                self.response({"org.overte.interface.dev": attributes})
            elif script == "mobile: activeAppInfo":
                self.response({"pid": 4321, "bundleId": "org.overte.interface.dev"})
            elif script == "mobile: pullFile":
                self.response(base64.b64encode(self.probe_content).decode("ascii"))
            else:
                if script == "mobile: terminateApp":
                    type(self).app_state = 1
                elif script in {"mobile: launchApp", "mobile: activateApp",
                                "mobile: startActivity"}:
                    type(self).app_state = 4
                elif script == "mobile: backgroundApp":
                    type(self).app_state = 2
                self.response(None)
        elif self.path.endswith("/element"):
            self.element_requests.append(payload)
            self.response({"element-6066-11e4-a52e-4f735466cecf": "element-private"})
        elif self.path.endswith("/actions"):
            self.action_payloads.append(payload)
            self.response(None)
        else:
            if (self.path.endswith("/element/element-private/click")
                    and self.restart_on_element_click and self.restart_marker is not None):
                self.restart_marker.touch()
            self.response(None)

    def do_DELETE(self) -> None:  # noqa: N802
        self.calls.append(("DELETE", self.path))
        self.response(None)

    def log_message(self, format_string: str, *arguments: object) -> None:
        pass


class AppiumAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="appium-adapter-test-")
        self.root = Path(self.temporary.name)
        AppiumHandler.calls = []
        AppiumHandler.executions = []
        AppiumHandler.action_payloads = []
        AppiumHandler.test_build_attested = True
        AppiumHandler.app_state = 1
        AppiumHandler.sound_commands = []
        AppiumHandler.reject_sound = False
        AppiumHandler.reject_webdriver = False
        AppiumHandler.source_content = (
            '<hierarchy><node content-desc="OverteTablet"/></hierarchy>')
        AppiumHandler.element_requests = []
        AppiumHandler.restart_on_element_click = False
        AppiumHandler.restart_marker = self.root / "android-restarted"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), AppiumHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.probe = self.root / "probe.json"
        self.write_probe()
        self.adb = self.root / "adb"
        self.adb.write_text(MOCK_ADB, encoding="utf-8")
        self.adb.chmod(0o700)
        url = f"http://127.0.0.1:{self.server.server_address[1]}"
        targets = {
            "schemaVersion": 1,
            "targets": [
                {
                    "selector": "phone-alias", "displayName": "Phone", "platform": "android",
                    "physical": False, "serverUrl": url, "appId": "org.overte.phone",
                    "capabilities": {"platformName": "Android", "appium:automationName": "UiAutomator2",
                                     "appium:autoLaunch": False},
                    "process": {"kind": "adb", "selector": "phone-mock"},
                    "scene": {"kind": "android-debug-e2e"},
                    "controls": {
                        "look": {"start": [0.8, 0.5], "end": [0.2, 0.5]},
                        "move": {"forward": {"mode": "hold", "start": [0.2, 0.8], "end": [0.2, 0.5]}},
                        "tablet": {"toggleAccessibilityId": "OverteTablet"},
                    },
                    "probe": {"kind": "host-file", "path": str(self.probe)},
                },
                {
                    "selector": "ipad-alias", "displayName": "iPad", "platform": "ios",
                    "physical": True, "serverUrl": url, "appId": "org.overte.interface.dev",
                    "capabilities": {"platformName": "iOS", "appium:automationName": "XCUITest",
                                     "appium:bundleId": "org.overte.interface.dev",
                                     "appium:udid": "private-mock-udid",
                                     "appium:platformVersion": "26.2.1",
                                     "appium:usePreinstalledWDA": True,
                                     "appium:updatedWDABundleId":
                                         "org.overte.WebDriverAgentRunner",
                                     "appium:autoLaunch": False},
                    "testBuild": {
                        "contract": "overte-ios-e2e-v1",
                        "contractVersion": 1,
                        "fixtureOrigin": url,
                        "probeScriptPath": "/overte_e2e_probe.js",
                        "resultsDirectory": "overte-e2e",
                        "launchArguments": ["--no-updater", "--no-login-suggestion"],
                        "launchEnvironment": {
                            "OVERTE_E2E_TEST_BUILD": "1",
                            "OVERTE_E2E_LOCALE": "en_US",
                        },
                    },
                    "scene": {"kind": "ios-test-build"},
                    "controls": {
                        "look": {"start": [0.8, 0.5], "end": [0.2, 0.5]},
                        "move": {"forward": {"mode": "hold", "start": [0.2, 0.8],
                                                "end": [0.2, 0.5]}},
                        "tablet": {"toggleAccessibilityId": "OverteTablet"},
                    },
                    "probe": {"kind": "ios-documents"},
                },
            ],
        }
        self.targets = targets
        self.config = self.root / "targets.json"
        self.config.write_text(json.dumps(targets), encoding="utf-8")
        self.environment = os.environ.copy()
        self.environment.update({
            "OVERTE_APPIUM_TARGETS": str(self.config),
            "OVERTE_DEVICE_STATE_ROOT": str(self.root / "state"),
            "OVERTE_DEVICE_ARTIFACT_DIR": str(self.root / "artifacts"),
            "OVERTE_E2E_CAPTURE_ARTIFACTS": "1",
            "OVERTE_ANDROID_ADB": str(self.adb),
            "OVERTE_MOCK_ANDROID_PROBE": str(self.probe),
            "OVERTE_MOCK_ANDROID_COMMAND_LOG": str(self.root / "android-commands.jsonl"),
            "OVERTE_MOCK_ANDROID_COMMAND_FILE": str(self.root / "android-command.json"),
            "OVERTE_MOCK_ANDROID_RESTART_MARKER": str(self.root / "android-restarted"),
        })
        (self.root / "artifacts").mkdir()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def write_probe(self):
        payload = json.dumps({
            "schemaVersion": 1, "sampleEpochMs": int(time.time() * 1000),
            "build": {"platform": "Mock", "version": "appium-contract",
                      "date": "1970-01-01"},
            "application": {"running": True, "foreground": True},
            "scene": {"url": "http://fixture/scene.json", "ready": True, "entityCount": 4},
            "avatar": {"position": {"x": 0, "y": 1, "z": 4}},
            "view": {"orientation": {"x": 0, "y": 0, "z": 0}},
            "tablet": {"open": False},
        })
        self.probe.write_text(payload, encoding="utf-8")
        AppiumHandler.probe_content = payload.encode("utf-8")

    def call(self, platform: str, action: str, *arguments: str) -> subprocess.CompletedProcess:
        self.write_probe()
        return subprocess.run([
            sys.executable, str(ADAPTER), "--platform", platform, action, *arguments,
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=self.environment, check=False)

    def configure_controlled_android(self) -> dict:
        payload = copy.deepcopy(self.targets)
        target = payload["targets"][0]
        target["physical"] = True
        target["capabilities"]["appium:udid"] = "phone-mock"
        target["process"]["selector"] = "phone-mock"
        target["probe"] = {
            "kind": "android-run-as",
            "relativePath": "files/overte-e2e/overte-probe.json",
        }
        target["clientControl"] = {
            "kind": "android-run-as-command",
            "relativePath": "files/overte-e2e/e2e-client-command.json",
        }
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        return target

    def configure_semantic_android(self) -> dict:
        payload = copy.deepcopy(self.targets)
        target = payload["targets"][0]
        target["controls"]["tablet"]["semanticUi"] = {"contractVersion": 1}
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        return target

    @staticmethod
    def semantic_source(screen: str = "tablet.home", controls: tuple[str, ...] = (
            "app.settings", "nav.close"), *, ready: bool = True,
            private_prefix: str = "org.overte.phone:id/") -> str:
        nodes = [
            f'<node class="android.widget.TextView" clickable="false" '
            f'resource-id="{private_prefix}{screen}" displayed="true" '
            f'enabled="{str(ready).lower()}"/>'
        ]
        nodes.extend(
            f'<node class="android.widget.Button" clickable="true" '
            f'resource-id="{private_prefix}{control}" displayed="true" enabled="true"/>'
            for control in controls)
        return "<hierarchy>" + "".join(nodes) + "</hierarchy>"

    def android_commands(self) -> list[dict]:
        path = self.root / "android-commands.jsonl"
        return ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                if path.exists() else [])

    def test_both_platform_manifests_satisfy_adapter_contract(self):
        for platform in ("android", "ios"):
            result = subprocess.run([
                sys.executable, str(VERIFIER), "--adapter-manifest",
                str(ROOT / "adapters/appium" / f"{platform}.json"), "--check-cleanup",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=self.environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            self.assertIn("for 1 target(s)", result.stdout)

        discovered = self.call("android", "discover")
        capabilities = json.loads(discovered.stdout)[0]["capabilities"]
        self.assertIn("telemetry.snapshot", capabilities)

    def test_android_operations_use_standard_webdriver_endpoints(self):
        target = ("--target", "phone-alias")
        for operation, values in (
            ("app.launch", {}), ("input.look", {}),
            ("scene.load", {"url": "overte-e2e://fixture/scene"}),
            ("input.move", {"direction": "forward", "durationSeconds": 0.1}),
            ("tablet.open", {}), ("accessibility.snapshot", {}),
            ("probe.snapshot", {}), ("artifact.screenshot", {}),
        ):
            result = self.call("android", "invoke", *target, "--operation", operation,
                               "--arguments", json.dumps(values))
            self.assertEqual(0, result.returncode, f"{operation}: {result.stdout}")
            self.assertNotIn("session-private", result.stdout)
        self.assertTrue((self.root / "artifacts/accessibility.xml").is_file())
        self.assertEqual(b"mock-png", (self.root / "artifacts/screenshot.png").read_bytes())
        paths = {path for _, path in AppiumHandler.calls}
        self.assertIn("/session/session-private/actions", paths)
        self.assertIn("/session/session-private/source", paths)
        self.assertIn(("mobile: startActivity", {
            "intent": "org.overte.phone/.E2eLauncherActivity", "stop": True, "wait": False,
        }), AppiumHandler.executions)
        self.assertIn(("mobile: activateApp", {"appId": "org.overte.phone"}),
                      AppiumHandler.executions)
        cleanup = self.call("android", "cleanup", *target)
        self.assertEqual(0, cleanup.returncode, cleanup.stdout)

    def test_android_debug_launcher_rejects_arbitrary_scene_urls(self):
        result = self.call(
            "android", "invoke", "--target", "phone-alias", "--operation", "scene.load",
            "--arguments", json.dumps({"url": "https://production.invalid/scene.json"}))
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("only the embedded fixture URL", result.stdout)

    def test_android_controlled_channel_gates_and_delivers_new_operations(self):
        uncontrolled = self.call("android", "discover")
        advertised = json.loads(uncontrolled.stdout)[0]["capabilities"]
        for capability in ("navigation.enter-domain", "asset.load", "sound.play"):
            self.assertNotIn(capability, advertised)

        self.configure_controlled_android()
        controlled = self.call("android", "discover")
        self.assertEqual(0, controlled.returncode, controlled.stdout)
        advertised = json.loads(controlled.stdout)[0]["capabilities"]
        for capability in ("navigation.enter-domain", "asset.load", "sound.play"):
            self.assertIn(capability, advertised)

        fixture = f"http://127.0.0.1:{self.server.server_address[1]}"
        operations = (
            ("navigation.enter-domain", {"url": "hifi://domain.example:40102"}),
            ("asset.load", {"assetId": "fixture.image", "url": fixture + "/image.png",
                            "entityName": "OVERTE_E2E_ASSET_LOAD_IMAGE"}),
            ("sound.play", {"schemaVersion": 1, "commandId": "sound-123",
                            "url": fixture + "/sound.wav",
                            "commandUrl": fixture + "/sound-command.json"}),
        )
        for operation, arguments in operations:
            result = self.call("android", "invoke", "--target", "phone-alias",
                               "--operation", operation,
                               "--arguments", json.dumps(arguments))
            self.assertEqual(0, result.returncode, f"{operation}: {result.stdout}")
        commands = self.android_commands()
        self.assertEqual("navigation-enter-domain", commands[0]["action"])
        self.assertEqual("hifi://domain.example:40102", commands[0]["url"])
        self.assertEqual({"action": "asset-load", "assetId": "fixture.image",
                          "entityName": "OVERTE_E2E_ASSET_LOAD_IMAGE",
                          "schemaVersion": 1, "url": fixture + "/image.png"},
                         {key: value for key, value in commands[1].items()
                          if key != "commandId"})
        self.assertEqual({"schemaVersion": 1, "commandId": "sound-123",
                          "action": "play", "soundUrl": fixture + "/sound.wav"},
                         AppiumHandler.sound_commands[-1])
        self.assertEqual({"schemaVersion": 1, "commandId": "sound-channel-sound-123",
                          "action": "sound-channel",
                          "url": fixture + "/sound-command.json"}, commands[2])

    def test_android_new_operations_fail_closed(self):
        invalid = self.call("android", "invoke", "--target", "phone-alias",
                            "--operation", "navigation.enter-domain", "--arguments",
                            json.dumps({"url": "https://domain.example:40102"}))
        self.assertEqual(2, invalid.returncode, invalid.stdout)
        self.assertIn("credential-free hifi URL", invalid.stdout)

        self.configure_controlled_android()
        AppiumHandler.reject_webdriver = True
        webdriver = self.call("android", "invoke", "--target", "phone-alias",
                              "--operation", "asset.load", "--arguments", json.dumps({
                                  "assetId": "fixture.image", "url": "http://fixture/image.png",
                                  "entityName": "OVERTE_E2E_ASSET_LOAD_IMAGE"}))
        self.assertEqual(2, webdriver.returncode, webdriver.stdout)
        self.assertEqual([], self.android_commands())
        AppiumHandler.reject_webdriver = False

        self.environment["OVERTE_MOCK_ANDROID_RESTART_AFTER_WRITE"] = "1"
        restarted = self.call("android", "invoke", "--target", "phone-alias",
                              "--operation", "navigation.enter-domain", "--arguments",
                              json.dumps({"url": "hifi://domain.example:40102"}))
        self.assertEqual(2, restarted.returncode, restarted.stdout)
        self.assertIn("process changed", restarted.stdout)

    def test_android_sound_rejects_wrong_or_failed_control_endpoint(self):
        self.configure_controlled_android()
        fixture = f"http://127.0.0.1:{self.server.server_address[1]}"
        arguments = {"schemaVersion": 1, "commandId": "sound-456",
                     "url": fixture + "/sound.wav", "commandUrl": fixture + "/wrong.json"}
        wrong = self.call("android", "invoke", "--target", "phone-alias",
                          "--operation", "sound.play", "--arguments", json.dumps(arguments))
        self.assertEqual(2, wrong.returncode, wrong.stdout)
        self.assertIn("controlled fixture origin and command path", wrong.stdout)
        arguments["commandUrl"] = fixture + "/sound-command.json"
        AppiumHandler.reject_sound = True
        rejected = self.call("android", "invoke", "--target", "phone-alias",
                             "--operation", "sound.play", "--arguments", json.dumps(arguments))
        self.assertEqual(2, rejected.returncode, rejected.stdout)
        self.assertEqual([], self.android_commands())

    def test_physical_android_debug_probe_uses_fixed_private_run_as_path(self):
        payload = copy.deepcopy(self.targets)
        target = payload["targets"][0]
        target["physical"] = True
        target["capabilities"]["appium:udid"] = "phone-mock"
        target["process"]["selector"] = "phone-mock"
        target["probe"] = {
            "kind": "android-run-as",
            "relativePath": "files/overte-e2e/overte-probe.json",
        }
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        result = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "probe.snapshot")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(1, json.loads(result.stdout)["schemaVersion"])

        target["probe"]["relativePath"] = "../shared_prefs/private.xml"
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        rejected = self.call("android", "discover")
        self.assertEqual(2, rejected.returncode, rejected.stdout)
        self.assertIn("fixed app-private debug path", rejected.stdout)

    def test_android_tablet_can_use_audited_fractional_touch_fallback(self):
        payload = copy.deepcopy(self.targets)
        payload["targets"][0]["controls"]["tablet"] = {
            "openPoint": [0.045, 0.25],
            "closePoint": [0.5, 0.965],
        }
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        result = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.open")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn(("mobile: clickGesture", {"x": 44, "y": 124}),
                      AppiumHandler.executions)
        result = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.close")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn(("mobile: clickGesture", {"x": 499, "y": 481}),
                      AppiumHandler.executions)

        payload["targets"][0]["controls"]["tablet"]["closePoint"] = [1.0, 0.25]
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        rejected = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.open")
        self.assertEqual(2, rejected.returncode, rejected.stdout)
        self.assertIn("finite fractions", rejected.stdout)

    def test_android_semantic_tablet_snapshot_and_real_element_activation(self):
        self.configure_semantic_android()
        AppiumHandler.source_content = self.semantic_source()
        discovered = self.call("android", "discover")
        capabilities = json.loads(discovered.stdout)[0]["capabilities"]
        self.assertIn("tablet.snapshot", capabilities)
        self.assertIn("tablet.activate", capabilities)

        opened = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.open")
        self.assertEqual(0, opened.returncode, opened.stdout)

        snapshot = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.snapshot")
        self.assertEqual(0, snapshot.returncode, snapshot.stdout)
        self.assertEqual({
            "contractVersion": 1,
            "schemaVersion": 1,
            "screenId": "tablet.home",
            "ready": True,
            "visibleControlIds": ["app.settings", "nav.close"],
            "selectedControlIds": [],
        }, json.loads(snapshot.stdout))

        activated = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.activate", "--arguments",
            json.dumps({"contractVersion": 1, "controlId": "app.settings"}))
        self.assertEqual(0, activated.returncode, activated.stdout)
        self.assertEqual({"performed": True}, json.loads(activated.stdout))
        self.assertIn({"using": "id", "value": "org.overte.phone:id/app.settings"},
                      AppiumHandler.element_requests)
        # A click result is not navigation evidence; without a changed native
        # tree the next independent snapshot still reports the prior screen.
        unchanged = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.snapshot")
        self.assertEqual("tablet.home", json.loads(unchanged.stdout)["screenId"])

        settings_controls = ("nav.home", "settings.audio", "settings.general",
                             "settings.security")
        AppiumHandler.source_content = self.semantic_source(
            "settings.home", settings_controls)
        settings = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.snapshot")
        self.assertEqual("settings.home", json.loads(settings.stdout)["screenId"])

        for control_id, screen_id in (
                ("settings.audio", "settings.audio"),
                ("settings.general", "settings.general"),
                ("settings.security", "settings.security")):
            entered = self.call(
                "android", "invoke", "--target", "phone-alias",
                "--operation", "tablet.activate", "--arguments",
                json.dumps({"contractVersion": 1, "controlId": control_id}))
            self.assertEqual(0, entered.returncode, entered.stdout)
            AppiumHandler.source_content = self.semantic_source(screen_id, ("nav.back",))
            nested = self.call(
                "android", "invoke", "--target", "phone-alias",
                "--operation", "tablet.snapshot")
            self.assertEqual(screen_id, json.loads(nested.stdout)["screenId"])
            returned = self.call(
                "android", "invoke", "--target", "phone-alias",
                "--operation", "tablet.activate", "--arguments",
                json.dumps({"contractVersion": 1, "controlId": "nav.back"}))
            self.assertEqual(0, returned.returncode, returned.stdout)
            AppiumHandler.source_content = self.semantic_source(
                "settings.home", settings_controls)

        home = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.activate", "--arguments",
            json.dumps({"contractVersion": 1, "controlId": "nav.home"}))
        self.assertEqual(0, home.returncode, home.stdout)
        AppiumHandler.source_content = self.semantic_source()
        returned_home = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.snapshot")
        self.assertEqual("tablet.home", json.loads(returned_home.stdout)["screenId"])
        closed = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.close")
        self.assertEqual(0, closed.returncode, closed.stdout)

    def test_android_semantic_tablet_reports_ready_and_actual_screen(self):
        self.configure_semantic_android()
        AppiumHandler.source_content = self.semantic_source(
            "settings.home", ("nav.home", "settings.audio", "settings.general",
                              "settings.security"), ready=False)
        result = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.snapshot")
        self.assertEqual(0, result.returncode, result.stdout)
        value = json.loads(result.stdout)
        self.assertEqual("settings.home", value["screenId"])
        self.assertFalse(value["ready"])
        self.assertEqual(["nav.home", "settings.audio", "settings.general",
                          "settings.security"], value["visibleControlIds"])

    def test_android_semantic_tablet_observes_forbidden_ids_for_policy_failure(self):
        self.configure_semantic_android()
        forbidden = ("settings.controllers", "settings.hmd-preferences",
                     "settings.vr-render-resolution")
        AppiumHandler.source_content = self.semantic_source(
            "settings.home", forbidden)
        result = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.snapshot")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(sorted(forbidden), json.loads(result.stdout)["visibleControlIds"])

    def test_android_semantic_tablet_rejects_missing_and_malformed_native_state(self):
        self.configure_semantic_android()
        cases = (
            ("<hierarchy>", "invalid XML"),
            ("<hierarchy/>", "exactly one screen"),
            (self.semantic_source()[:-12]
             + '<node resource-id="settings.home" displayed="true"/></hierarchy>',
             "exactly one screen"),
        )
        for source, expected in cases:
            with self.subTest(expected=expected):
                AppiumHandler.source_content = source
                result = self.call(
                    "android", "invoke", "--target", "phone-alias",
                    "--operation", "tablet.snapshot")
                self.assertEqual(2, result.returncode, result.stdout)
                self.assertIn(expected, result.stdout)

        AppiumHandler.source_content = self.semantic_source(
            "settings.home", ("nav.home",))
        missing = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.activate", "--arguments",
            json.dumps({"contractVersion": 1, "controlId": "settings.general"}))
        self.assertEqual(2, missing.returncode, missing.stdout)
        self.assertIn("not visible", missing.stdout)

    def test_android_semantic_tablet_detects_process_restart_and_redacts_selectors(self):
        self.configure_semantic_android()
        private_prefix = "private-target-selector:id/"
        AppiumHandler.source_content = self.semantic_source(private_prefix=private_prefix)
        snapshot = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.snapshot")
        self.assertEqual(0, snapshot.returncode, snapshot.stdout)
        self.assertNotIn("private-target-selector", snapshot.stdout)

        AppiumHandler.restart_on_element_click = True
        restarted = self.call(
            "android", "invoke", "--target", "phone-alias",
            "--operation", "tablet.activate", "--arguments",
            json.dumps({"contractVersion": 1, "controlId": "app.settings"}))
        self.assertEqual(2, restarted.returncode, restarted.stdout)
        self.assertIn("process changed", restarted.stdout)
        self.assertNotIn("private-target-selector", restarted.stdout)

    def test_semantic_tablet_configuration_is_fail_closed_and_android_only(self):
        cases = (
            (0, {"contractVersion": 2}, "contract version 1"),
            (1, {"contractVersion": 1}, "currently Android-only"),
        )
        for index, semantic, expected in cases:
            with self.subTest(expected=expected):
                payload = copy.deepcopy(self.targets)
                payload["targets"][index]["controls"]["tablet"]["semanticUi"] = semantic
                self.config.write_text(json.dumps(payload), encoding="utf-8")
                result = self.call(
                    "android" if index == 0 else "ios", "discover")
                self.assertEqual(2, result.returncode, result.stdout)
                self.assertIn(expected, result.stdout)

    def test_ios_initial_launch_sets_arguments_and_background_preserves_process(self):
        target = ("--target", "ipad-alias")
        identities = []
        for operation in ("app.launch", "app.process", "lifecycle.background",
                          "app.launch", "app.process"):
            result = self.call("ios", "invoke", *target, "--operation", operation)
            self.assertEqual(0, result.returncode, f"{operation}: {result.stdout}")
            if operation == "app.process":
                identities.append(json.loads(result.stdout)["identity"])
        self.assertEqual(["4321", "4321"], identities)
        self.assertIn(("mobile: launchApp", {
            "bundleId": "org.overte.interface.dev",
            "arguments": ["--no-updater", "--no-login-suggestion"],
            "environment": {"OVERTE_E2E_TEST_BUILD": "1", "OVERTE_E2E_LOCALE": "en_US"},
        }), AppiumHandler.executions)
        self.assertNotIn(("mobile: terminateApp", {"bundleId": "org.overte.interface.dev"}),
                         AppiumHandler.executions)
        self.assertIn(("mobile: activateApp", {"bundleId": "org.overte.interface.dev"}),
                      AppiumHandler.executions)
        self.assertEqual(1, sum(script == "mobile: launchApp"
                                for script, _ in AppiumHandler.executions))
        self.assertIn(("mobile: activeAppInfo", {}), AppiumHandler.executions)
        self.assertIn(("mobile: backgroundApp", {"seconds": -1}),
                      AppiumHandler.executions)

    def test_ios_test_build_relaunches_with_controlled_probe_and_pulls_documents(self):
        target = ("--target", "ipad-alias")
        scene_url = f"http://127.0.0.1:{self.server.server_address[1]}/scene.json"
        loaded = self.call(
            "ios", "invoke", *target, "--operation", "scene.load",
            "--arguments", json.dumps({"url": scene_url}))
        self.assertEqual(0, loaded.returncode, loaded.stdout)
        self.assertEqual("fixture-markers", json.loads(loaded.stdout)["verification"])
        self.assertIn(("mobile: terminateApp", {"bundleId": "org.overte.interface.dev"}),
                      AppiumHandler.executions)
        self.assertIn(("mobile: launchApp", {
            "bundleId": "org.overte.interface.dev",
            "arguments": [
                "--no-updater", "--no-login-suggestion",
                "--url", scene_url,
                "--testScript", f"http://127.0.0.1:{self.server.server_address[1]}"
                                "/overte_e2e_probe.js",
                "--testResultsLocation", "overte-e2e",
            ],
            "environment": {"OVERTE_E2E_TEST_BUILD": "1", "OVERTE_E2E_LOCALE": "en_US"},
        }), AppiumHandler.executions)

        snapshot = self.call("ios", "invoke", *target, "--operation", "probe.snapshot")
        self.assertEqual(0, snapshot.returncode, snapshot.stdout)
        self.assertEqual(1, json.loads(snapshot.stdout)["schemaVersion"])
        self.assertIn(("mobile: pullFile", {
            "remotePath": "@org.overte.interface.dev:documents/"
                          "overte-e2e/overte-probe.json",
        }), AppiumHandler.executions)

    def test_ios_test_build_rejects_non_fixture_scene_before_launch(self):
        result = self.call(
            "ios", "invoke", "--target", "ipad-alias", "--operation", "scene.load",
            "--arguments", json.dumps({"url": "https://production.invalid/scene.json"}))
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("configured fixtureOrigin", result.stdout)
        self.assertFalse(any(script == "mobile: launchApp"
                             for script, _ in AppiumHandler.executions))

    def test_ios_behavior_configuration_fails_closed_without_exact_contract(self):
        invalid_cases = (
            (lambda value: value.pop("testBuild"), "fail-closed testBuild contract"),
            (lambda value: value["testBuild"].__setitem__("contractVersion", 2),
             "contractVersion must be 1"),
            (lambda value: value["capabilities"].__setitem__("appium:autoLaunch", True),
             "autoLaunch=false"),
            (lambda value: value["probe"].__setitem__("kind", "appium-pull-file"),
             "probe.kind=ios-documents"),
            (lambda value: value["testBuild"]["launchArguments"].append("--url"),
             "must not override --url"),
            (lambda value: value["testBuild"].__setitem__("probeUrl", "https://invalid"),
             "unsupported fields"),
        )
        for mutation, expected in invalid_cases:
            with self.subTest(expected=expected):
                payload = copy.deepcopy(self.targets)
                mutation(payload["targets"][1])
                self.config.write_text(json.dumps(payload), encoding="utf-8")
                result = self.call("ios", "discover")
                self.assertEqual(2, result.returncode, result.stdout)
                self.assertIn(expected, result.stdout)
        self.config.write_text(json.dumps(self.targets), encoding="utf-8")

    def test_linux_ios_configuration_requires_remotexpc_session_strategy(self):
        invalid_cases = (
            (lambda caps: caps.pop("appium:udid"), "explicit private appium:udid"),
            (lambda caps: caps.__setitem__("appium:platformVersion", "17.7"),
             "platformVersion 18 or newer"),
            (lambda caps: caps.pop("appium:usePreinstalledWDA"),
             "preinstalled or external WDA"),
            (lambda caps: caps.pop("appium:updatedWDABundleId"),
             "updatedWDABundleId"),
            (lambda caps: caps.__setitem__("appium:xcodeOrgId", "TEAM"),
             "Xcode-only capabilities"),
        )
        for mutation, expected in invalid_cases:
            with self.subTest(expected=expected):
                payload = copy.deepcopy(self.targets)
                mutation(payload["targets"][1]["capabilities"])
                self.config.write_text(json.dumps(payload), encoding="utf-8")
                result = self.call("ios", "discover")
                self.assertEqual(2, result.returncode, result.stdout)
                self.assertIn(expected, result.stdout)
        self.config.write_text(json.dumps(self.targets), encoding="utf-8")

    def test_linux_ios_artifact_receipt_binds_both_signed_install_paths(self):
        payload = copy.deepcopy(self.targets)
        target = payload["targets"][1]
        overte = self.root / "Overte-E2E-signed.ipa"
        wda = self.root / "WebDriverAgentRunner-signed.ipa"
        overte.write_bytes(b"signed overte fixture")
        wda.write_bytes(b"signed wda fixture")
        target["capabilities"].update({
            "appium:app": str(overte),
            "appium:prebuiltWDAPath": str(wda),
        })
        receipt = self.root / "fedora-artifacts-receipt.json"
        receipt.write_text(json.dumps({
            "schemaVersion": 1,
            "contract": "overte-ios-fedora-e2e-receipt-v1",
            "sourceRevision": "a" * 40,
            "overte": {
                "path": str(overte),
                "sha256": hashlib.sha256(overte.read_bytes()).hexdigest(),
                "bundleId": "org.overte.interface.dev",
            },
            "wda": {
                "path": str(wda),
                "sha256": hashlib.sha256(wda.read_bytes()).hexdigest(),
                "bundleId": "org.overte.WebDriverAgentRunner.xctrunner",
            },
            "toolchain": {
                "xcuitestDriver": "12.8.0",
                "remoteXpc": "5.15.3",
                "webdriverAgent": "16.8.0",
            },
        }), encoding="utf-8")
        target["artifactReceipt"] = str(receipt)
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        try:
            result = self.call(
                "ios", "invoke", "--target", "ipad-alias", "--operation", "app.launch"
            )
            self.assertEqual(0, result.returncode, result.stdout)
            receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
            receipt_value["wda"]["sha256"] = "0" * 64
            receipt.write_text(json.dumps(receipt_value), encoding="utf-8")
            result = self.call("ios", "discover")
            self.assertEqual(0, result.returncode, result.stdout)
            state = self.root / "state" / "appium-ios" / hashlib.sha256(
                b"ipad-alias"
            ).hexdigest()
            # A changed receipt invalidates the target fingerprint. Removing the
            # prior session forces the next invocation through the byte gate.
            for session_file in state.parent.rglob("session.json"):
                session_file.unlink()
            result = self.call(
                "ios", "invoke", "--target", "ipad-alias", "--operation", "app.launch"
            )
            self.assertEqual(2, result.returncode, result.stdout)
            self.assertIn("failed its receipt SHA-256", result.stdout)
        finally:
            self.config.write_text(json.dumps(self.targets), encoding="utf-8")

    def test_plain_ios_target_remains_lifecycle_only(self):
        payload = copy.deepcopy(self.targets)
        target = payload["targets"][1]
        target.pop("testBuild")
        target.pop("scene")
        target.pop("probe")
        target["controls"] = {}
        target["capabilities"].pop("appium:autoLaunch")
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        try:
            result = self.call("ios", "discover")
            self.assertEqual(0, result.returncode, result.stdout)
            capabilities = json.loads(result.stdout)[0]["capabilities"]
            self.assertIn("app.launch", capabilities)
            for unavailable in ("scene.load", "probe.snapshot", "input.look",
                                "input.move", "tablet.open", "tablet.close"):
                self.assertNotIn(unavailable, capabilities)
        finally:
            self.config.write_text(json.dumps(self.targets), encoding="utf-8")

    def test_physical_ios_test_build_requires_runtime_plist_attestation(self):
        AppiumHandler.test_build_attested = False
        result = self.call(
            "ios", "invoke", "--target", "ipad-alias", "--operation", "app.launch")
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("does not attest the E2E test-build contract", result.stdout)


if __name__ == "__main__":
    unittest.main()
