#!/usr/bin/env python3
"""Device-free tests for the shared Android/iOS Appium transport."""

from __future__ import annotations

import importlib.util
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


DEVICE_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = DEVICE_ROOT / "adapters/appium/adapter.py"
SPEC = importlib.util.spec_from_file_location("overte_shared_appium", ADAPTER_PATH)
assert SPEC and SPEC.loader
APPIUM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPIUM)


def target(platform: str, *, enabled: bool = True, physical: bool = False) -> dict:
    platform_name = "Android" if platform == "android" else "iOS"
    automation = "UiAutomator2" if platform == "android" else "XCUITest"
    return {
        "selector": f"shared-{platform}",
        "displayName": f"Shared {platform}",
        "platform": platform,
        "physical": physical,
        "enabled": enabled,
        "serverUrl": "http://127.0.0.1:4723",
        "appId": "org.overte.example",
        "capabilities": {
            "platformName": platform_name,
            "appium:automationName": automation,
            "appium:autoLaunch": False,
        },
        "controls": {
            "look": {"start": [.7, .4], "end": [.3, .4],
                     "mode": "swipe", "durationSeconds": .5},
            "move": {
                "forward": {"start": [.2, .8], "end": [.2, .6],
                            "mode": "hold", "durationSeconds": .5},
            },
            "tablet": {
                "openAccessibilityId": "TabletOpen",
                "closeAccessibilityId": "TabletClose",
                "semanticUi": {"contractVersion": 1},
            },
        },
    }


class FakeClient:
    def __init__(self, source: str = "") -> None:
        self.source = source
        self.calls: list[tuple] = []

    def call(self, method: str, path: str, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/source"):
            return self.source
        if path.endswith("/window/rect"):
            return {"x": 10, "y": 20, "width": 1000, "height": 500}
        if path.endswith("/screenshot"):
            return "c2NyZWVuc2hvdA=="
        if method == "POST" and path == "/session":
            return {"sessionId": "shared-session"}
        if method == "POST" and path.endswith("/element"):
            return {"element-6066-11e4-a52e-4f735466cecf": "element"}
        return {}

    def execute(self, session: str, script: str, arguments: dict):
        self.calls.append(("EXECUTE", session, script, arguments))
        return 4 if script == "mobile: queryAppState" else None


class AppiumAdapterTest(unittest.TestCase):
    def load(self, platform: str, targets: list[object]) -> APPIUM.AppiumAdapter:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.json"
            path.write_text(json.dumps({"schemaVersion": 1, "targets": targets}))
            path.chmod(0o600)
            with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": str(path)}):
                return APPIUM.AppiumAdapter(platform)

    def run_with_payload(self, payload: object) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.json"
            path.write_text(json.dumps(payload))
            path.chmod(0o600)
            environment = os.environ.copy()
            environment["OVERTE_APPIUM_TARGETS"] = str(path)
            return subprocess.run(
                [sys.executable, str(ADAPTER_PATH), "--platform", "android", "discover"],
                text=True, capture_output=True, check=False, env=environment)

    def test_manifests_share_one_implementation(self):
        for platform in ("android", "ios"):
            manifest = json.loads((DEVICE_ROOT / f"adapters/appium/{platform}.json").read_text())
            self.assertEqual(1, manifest["schemaVersion"])
            self.assertEqual(["adapter.py", "--platform", platform], manifest["command"])

    def test_peer_platform_entries_are_ignored_before_validation(self):
        peer = {"platform": "ios", "unexpected": "stale peer value"}
        adapter = self.load("android", [peer, target("android")])
        self.assertEqual(["shared-android"], list(adapter.targets))

    def test_platform_specific_fields_fail_closed(self):
        configured = target("ios")
        configured["unexpectedPlatformField"] = {}
        with self.assertRaisesRegex(RuntimeError, "unsupported fields"):
            self.load("ios", [configured])

    def test_non_object_json_root_exits_cleanly(self):
        result = self.run_with_payload([])
        self.assertEqual(2, result.returncode)
        self.assertIn("unsupported Appium target configuration schema", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_enabled_is_required(self):
        configured = target("android")
        configured.pop("enabled")
        with self.assertRaisesRegex(RuntimeError, "enabled flags"):
            self.load("android", [configured])

    def test_private_configuration_permissions_and_location_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.json"
            path.write_text(json.dumps({"schemaVersion": 1, "targets": []}))
            path.chmod(0o644)
            with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": str(path)}):
                with self.assertRaisesRegex(RuntimeError, "mode 0600"):
                    APPIUM.AppiumAdapter("android")
            path.chmod(0o600)
            link = Path(directory) / "targets-link.json"
            link.symlink_to(path)
            with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": str(link)}):
                with self.assertRaisesRegex(RuntimeError, "symbolic links"):
                    APPIUM.AppiumAdapter("android")
            hardlink = Path(directory) / "targets-hardlink.json"
            os.link(path, hardlink)
            with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": str(path)}):
                with self.assertRaisesRegex(RuntimeError, "ordinary private file"):
                    APPIUM.AppiumAdapter("android")
        with mock.patch.dict(os.environ, {
                "OVERTE_APPIUM_TARGETS": str(
                    DEVICE_ROOT / "adapters/appium/targets.example.json")}):
            with self.assertRaisesRegex(RuntimeError, "outside the repository"):
                APPIUM.AppiumAdapter("android")

    def test_private_configuration_path_must_already_be_absolute(self):
        with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": "targets.json"}):
            with self.assertRaisesRegex(RuntimeError, "absolute private path"):
                APPIUM.AppiumAdapter("android")

    def test_transport_requires_https_away_from_loopback(self):
        for accepted in ("http://127.0.0.1:4723", "http://[::1]:4723",
                         "http://localhost:4723", "https://appium.example.invalid"):
            with self.subTest(accepted=accepted):
                self.assertEqual(accepted, APPIUM.WebDriver(accepted).server_url)
        with self.assertRaisesRegex(RuntimeError, "restricted to loopback"):
            APPIUM.WebDriver("http://appium.example.invalid")

    def test_points_and_configured_durations_are_bounded(self):
        for value in ([1.0, .5], [float("nan"), .5]):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                APPIUM.require_point(value, "point")
        for value in (0, 10.1, float("inf")):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                APPIUM.bounded_seconds(value, "duration")

    def test_physical_session_fails_before_network_access(self):
        adapter = self.load("android", [target("android", physical=True)])
        with mock.patch.object(APPIUM, "WebDriver") as webdriver:
            with self.assertRaisesRegex(RuntimeError, "platform integration"):
                adapter.ensure_session("shared-android")
            webdriver.assert_not_called()

    def test_discovery_advertises_only_configured_shared_operations(self):
        configured = target("android")
        configured["controls"].pop("move")
        adapter = self.load("android", [configured])
        discovered = adapter.discover()[0]
        self.assertNotIn("input.move", discovered["capabilities"])
        self.assertIn("tablet.snapshot", discovered["capabilities"])
        self.assertNotIn("app.process", discovered["capabilities"])
        self.assertNotIn("probe.snapshot", discovered["capabilities"])

    def test_unadvertised_operation_fails_before_session_creation(self):
        configured = target("android")
        adapter = self.load("android", [configured])
        with mock.patch.object(adapter, "ensure_session") as ensure:
            with self.assertRaisesRegex(RuntimeError, "direction is not configured"):
                adapter.invoke("shared-android", "input.move", {
                    "direction": "backward", "durationSeconds": .5,
                })
            ensure.assert_not_called()

    def test_every_advertised_invoke_path_performs_its_w3c_operation(self):
        adapter = self.load("android", [target("android")])
        configured = adapter.targets["shared-android"]
        source = """<hierarchy>
          <node resource-id="tablet.home" enabled="true"/>
          <node content-desc="app.settings" clickable="true" enabled="true"/>
        </hierarchy>"""
        client = FakeClient(source)
        invoked: set[str] = set()
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "application.bin"
            artifact.write_bytes(b"application")
            environment = {"OVERTE_DEVICE_ARTIFACT_DIR": directory}
            with mock.patch.dict(os.environ, environment), mock.patch.object(
                    adapter, "ensure_session",
                    return_value=(configured, client, "shared-session")):
                operations = {
                    "app.foreground": {},
                    "app.install": {"path": str(artifact)},
                    "app.launch": {},
                    "artifact.screenshot": {},
                    "input.look": {"horizontal": .5, "vertical": 0},
                    "input.move": {"direction": "forward", "durationSeconds": .5},
                    "tablet.close": {},
                    "tablet.open": {},
                    "tablet.snapshot": {},
                    "tablet.activate": {"contractVersion": 1,
                                        "controlId": "app.settings"},
                }
                for operation, arguments in operations.items():
                    with self.subTest(operation=operation):
                        self.assertIsInstance(
                            adapter.invoke("shared-android", operation, arguments), dict)
                        invoked.add(operation)
        self.assertEqual(set(adapter.capabilities(configured)), invoked)
        self.assertTrue(any(call[0] == "EXECUTE" for call in client.calls))
        self.assertTrue(any(call[1].endswith("/actions") for call in client.calls
                            if len(call) >= 2 and isinstance(call[1], str)))
        action_body = next(call[2] for call in client.calls
                           if len(call) >= 3 and isinstance(call[1], str)
                           and call[1].endswith("/actions")
                           and call[2]["actions"][0]["id"] == "overte-touch"
                           and any(action["type"] == "pause"
                                   for action in call[2]["actions"][0]["actions"]))
        actions = action_body["actions"][0]["actions"]
        self.assertEqual(
            {"type": "pointerMove", "duration": 0, "origin": "viewport",
             "x": 209, "y": 419}, actions[0])
        self.assertEqual(
            {"type": "pointerMove", "duration": 150, "origin": "viewport",
             "x": 209, "y": 319}, actions[2])
        self.assertEqual({"type": "pause", "duration": 500}, actions[3])

    def test_session_state_is_reused_and_cleanup_is_idempotent(self):
        adapter = self.load("android", [target("android")])
        client = FakeClient()
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
                os.environ, {"OVERTE_DEVICE_STATE_ROOT": state_root}), mock.patch.object(
                    APPIUM, "WebDriver", return_value=client):
            first = adapter.ensure_session("shared-android")
            second = adapter.ensure_session("shared-android")
            self.assertEqual("shared-session", first[2])
            self.assertEqual(first[2], second[2])
            self.assertEqual(1, sum(call[:2] == ("POST", "/session")
                                    for call in client.calls))
            self.assertEqual({"cleaned": True}, adapter.cleanup("shared-android"))
            self.assertEqual({"cleaned": True}, adapter.cleanup("shared-android"))
            self.assertEqual(1, sum(call[0] == "DELETE" for call in client.calls))

    def test_cleanup_failure_retains_private_session_state(self):
        adapter = self.load("android", [target("android")])

        class FailingDeleteClient(FakeClient):
            def call(self, method: str, path: str, body=None):
                if method == "DELETE":
                    raise RuntimeError("simulated transport failure")
                return super().call(method, path, body)

        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
                os.environ, {"OVERTE_DEVICE_STATE_ROOT": state_root}):
            adapter.save_session("shared-android", "shared-session")
            state_path = adapter.state_path("shared-android")
            with mock.patch.object(APPIUM, "WebDriver", return_value=FailingDeleteClient()):
                with self.assertRaisesRegex(RuntimeError, "simulated transport failure"):
                    adapter.cleanup("shared-android")
            self.assertTrue(state_path.is_file())
            self.assertEqual("shared-session", adapter.read_session("shared-android")["sessionId"])

    def test_session_state_rejects_symlinks_and_hardlinks(self):
        adapter = self.load("android", [target("android")])
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
                os.environ, {"OVERTE_DEVICE_STATE_ROOT": state_root}):
            path = adapter.state_path("shared-android")
            path.write_text('{"sessionId":"shared-session"}')
            path.chmod(0o600)
            second = path.with_name("session-hardlink.json")
            os.link(path, second)
            with self.assertRaisesRegex(RuntimeError, "private ordinary file"):
                adapter.read_session("shared-android")
            second.unlink()
            path.unlink()
            target_path = path.with_name("session-target.json")
            target_path.write_text('{"sessionId":"shared-session"}')
            target_path.chmod(0o600)
            path.symlink_to(target_path)
            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                adapter.read_session("shared-android")

    def semantic_adapter(self, platform: str) -> APPIUM.AppiumAdapter:
        adapter = APPIUM.AppiumAdapter.__new__(APPIUM.AppiumAdapter)
        adapter.platform = platform
        return adapter

    def test_android_semantic_tree_uses_only_contract_ids(self):
        source = """<hierarchy>
          <node resource-id="tablet.home" enabled="true"/>
          <node content-desc="app.settings" clickable="true" enabled="true"
                elementId="settings-element"/>
          <node content-desc="unrelated.private.text"/>
        </hierarchy>"""
        snapshot, actionable = self.semantic_adapter("android").semantic_snapshot(
            FakeClient(source), "session")
        self.assertEqual("tablet.home", snapshot["screenId"])
        self.assertEqual(["app.settings"], snapshot["visibleControlIds"])
        self.assertEqual({"app.settings": ("accessibility id", "app.settings")}, actionable)

    def test_ios_prefixed_semantic_tree_is_reduced_to_contract(self):
        source = """<AppiumAUT>
          <XCUIElementTypeOther name="OverteTabletScreen.settings.home" visible="true"/>
          <XCUIElementTypeButton name="OverteTabletControl.settings.audio"
                 visible="true" enabled="true"/>
          <XCUIElementTypeOther name="OverteTabletReady.settings.home" visible="true"/>
        </AppiumAUT>"""
        snapshot, actionable = self.semantic_adapter("ios").semantic_snapshot(
            FakeClient(source), "session")
        self.assertTrue(snapshot["ready"])
        self.assertEqual(["settings.audio"], snapshot["visibleControlIds"])
        self.assertEqual({"settings.audio": (
            "accessibility id", "OverteTabletControl.settings.audio")}, actionable)

    def test_ios_retries_only_a_known_transient_tree_shape(self):
        sources = [
            "<AppiumAUT/>",
            """<AppiumAUT>
              <XCUIElementTypeOther name="OverteTabletScreen.tablet.home" visible="true"/>
              <XCUIElementTypeOther name="OverteTabletReady.tablet.home" visible="true"/>
            </AppiumAUT>""",
        ]
        client = FakeClient()
        client.call = lambda *_args: sources.pop(0)
        with mock.patch.object(APPIUM.time, "sleep") as pause:
            snapshot, _ = self.semantic_adapter("ios").semantic_snapshot(client, "session")
        self.assertEqual("tablet.home", snapshot["screenId"])
        pause.assert_called_once_with(0.1)

    def test_ios_unknown_marker_is_not_retried(self):
        source = ('<AppiumAUT><XCUIElementTypeOther '
                  'name="OverteTabletScreen.unknown.screen" visible="true"/></AppiumAUT>')
        with mock.patch.object(APPIUM.time, "sleep") as pause:
            with self.assertRaisesRegex(RuntimeError, "unknown screen"):
                self.semantic_adapter("ios").semantic_snapshot(FakeClient(source), "session")
        pause.assert_not_called()

    def test_semantic_parser_rejects_ambiguous_and_declared_xml(self):
        adapter = self.semantic_adapter("android")
        for source in ("<root><node resource-id='tablet.home'/><node resource-id='settings.home'/></root>",
                       "<!DOCTYPE root><root/>"):
            with self.subTest(source=source), self.assertRaises(RuntimeError):
                adapter.semantic_snapshot(FakeClient(source), "session")

    def test_import_closure_is_standard_library_and_shared_device_code(self):
        tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
        roots = {
            node.module.split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
        }
        roots.update(alias.name.split(".")[0] for node in ast.walk(tree)
                     if isinstance(node, ast.Import) for alias in node.names)
        self.assertEqual({
            "__future__", "adapters", "argparse", "base64", "contracts", "ipaddress",
            "json", "math", "os", "pathlib", "stat", "sys", "tempfile", "time",
            "urllib", "xml",
        }, roots)


if __name__ == "__main__":
    unittest.main()
