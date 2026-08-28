#!/usr/bin/env python3
"""Device-free Appium/XCUITest contract and full iOS baseline tests."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest import mock
from urllib.error import HTTPError


DEVICE_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = DEVICE_ROOT / "adapters" / "appium" / "adapter.py"
SPEC = importlib.util.spec_from_file_location("overte_appium_adapter", ADAPTER_PATH)
assert SPEC and SPEC.loader
APPIUM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPIUM)


def snapshot(*, orientation_y: float = 0.0, position_y: float = 2.0,
             position_z: float = 4.0, in_air: bool = False,
             flying: bool = False, tablet_open: bool = False,
             sampled: int | None = None) -> dict:
    return {
        "schemaVersion": 1,
        "sampleEpochMs": sampled if sampled is not None else int(time.time() * 1000),
        "build": {"platform": "ios", "version": "e2e", "date": "2026-08-25"},
        "application": {"running": True, "foreground": True},
        "scene": {"ready": True, "entityCount": 4, "fixtureMarkerCount": 4},
        "avatar": {
            "position": {"x": 0.0, "y": position_y, "z": position_z},
            "inAir": in_air, "flying": flying, "flyingEnabled": True,
        },
        "view": {"orientation": {"x": 0.0, "y": orientation_y, "z": 0.0}},
        "tablet": {"open": tablet_open},
    }


def ios_target(*, enabled: bool = True) -> dict:
    return {
        "selector": "private-ipad",
        "displayName": "Private iPad",
        "platform": "ios",
        "physical": True,
        "enabled": enabled,
        "artifactMode": "signed-ipa",
        "serverUrl": "http://127.0.0.1:4723",
        "appId": "org.overte.e2e",
        "capabilities": {
            "platformName": "iOS",
            "appium:automationName": "XCUITest",
            "appium:udid": "private-device-id",
            "appium:platformVersion": "18.6",
            "appium:bundleId": "org.overte.e2e",
            "appium:autoLaunch": False,
            "appium:enforceAppInstall": False,
            "appium:usePreinstalledWDA": True,
            "appium:updatedWDABundleId": "org.overte.wda",
        },
        "testBuild": {
            "contract": "overte-ios-e2e-v1",
            "contractVersion": 1,
            "fixtureOrigin": "http://lab.example:18080",
            "scenePath": "/scene.json?location=%2F0%2C2%2C4%2F0%2C0%2C0%2C1",
            "probeScriptPath": "/overte_e2e_probe.js",
            "resultsDirectory": "overte-e2e",
            "launchArguments": ["--no-updater"],
            "launchEnvironment": {"OVERTE_E2E_TEST_BUILD": "1"},
        },
        "scene": {"kind": "ios-test-build"},
        "controls": {
            "look": {"start": [0.75, 0.45], "end": [0.35, 0.45],
                     "durationSeconds": 0.7},
            "move": {"forward": {"mode": "hold", "start": [0.2, 0.78],
                                  "end": [0.2, 0.55], "durationSeconds": 1.5}},
            "verticalLocomotion": {
                "jumpPoint": [0.9, 0.8],
                "jumpPressSeconds": 0.1,
                "flightSecondPressDelaySeconds": 0.25,
            },
            "tablet": {"openAccessibilityId": "OverteTabletOpen",
                       "closeAccessibilityId": "OverteTabletClose"},
        },
        "probe": {"kind": "ios-documents"},
        "soundControl": {"kind": "fixture-http", "commandPath": "/sound-command.json"},
    }


def prebuilt_wda(root: Path) -> Path:
    application = root / "WebDriverAgentRunner-Runner.app"
    application.mkdir(mode=0o700)
    plist = application / "Info.plist"
    plist.write_bytes(b"private fake plist")
    plist.chmod(0o600)
    executable = application / "WebDriverAgentRunner-Runner"
    executable.write_bytes(b"private fake executable")
    executable.chmod(0o700)
    return application


class FakeXCUITest:
    """Small stateful WebDriver double; no Appium client library is involved."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, object]] = []
        self.app_state = 1
        self.launch_state = 4
        self.pid = 4123
        self.bundle = "org.overte.e2e"
        self.orientation_y = 0.0
        self.position_y = 2.0
        self.position_z = 4.0
        self.in_air = False
        self.flying = False
        self.jump_snapshots_remaining = 0
        self.tablet_open = False
        self.last_identifier: str | None = None

    def current_snapshot(self) -> dict:
        value = snapshot(orientation_y=self.orientation_y,
                         position_y=self.position_y,
                         position_z=self.position_z,
                         in_air=self.in_air, flying=self.flying,
                         tablet_open=self.tablet_open)
        if self.jump_snapshots_remaining > 0:
            self.jump_snapshots_remaining -= 1
            if self.jump_snapshots_remaining == 0:
                self.position_y = 2.0
                self.in_air = False
                self.flying = False
        return value

    def execute(self, session: str, script: str, arguments: dict | None = None) -> object:
        payload = arguments or {}
        self.events.append(("execute", script, payload))
        if script == "mobile: queryAppState":
            return self.app_state
        if script == "mobile: activeAppInfo":
            return {"pid": self.pid, "bundleId": self.bundle}
        if script == "mobile: launchApp":
            self.app_state = self.launch_state
            return None
        if script == "mobile: activateApp":
            self.app_state = 4
            return None
        if script == "mobile: terminateApp":
            self.app_state = 1
            return True
        if script == "mobile: pullFile":
            raw = json.dumps(self.current_snapshot()).encode("utf-8")
            return base64.b64encode(raw).decode("ascii")
        if script == "mobile: deviceInfo":
            return {"isSimulator": False, "udid": "private-device-id",
                    "productVersion": "18.6.0"}
        if script == "mobile: listApps":
            return {
                self.bundle: {
                    "CFBundleIdentifier": self.bundle,
                    "UIFileSharingEnabled": True,
                    "OverteE2ETestBuildContractVersion": 1,
                },
                "org.overte.wda.xctrunner": {
                    "CFBundleIdentifier": "org.overte.wda.xctrunner",
                    "OverteE2EWebDriverAgentVersion": "16.8.0",
                    "OverteE2EXCUITestDriverVersion": "12.8.0",
                },
            }
        raise AssertionError(f"unexpected execute script: {script}")

    def call(self, method: str, path: str, payload: dict | None = None) -> object:
        body = payload or {}
        self.events.append((method, path, body))
        if method == "GET" and path.endswith("/window/rect"):
            return {"x": 0, "y": 0, "width": 1000, "height": 1000}
        if method == "GET" and path.endswith("/source"):
            identifier = "OverteTabletClose" if self.tablet_open else "OverteTabletOpen"
            return f'<AppiumAUT><XCUIElement name="{identifier}"/></AppiumAUT>'
        if method == "POST" and path.endswith("/actions"):
            source = body["actions"][0]
            first = source["actions"][0]
            if source["id"] == "overte-ios-vertical-locomotion":
                presses = sum(1 for action in source["actions"]
                              if action["type"] == "pointerDown")
                if presses == 1:
                    self.position_y = 2.5
                    self.in_air = True
                    self.flying = False
                    self.jump_snapshots_remaining = 1
                elif presses == 2:
                    self.position_y = 4.0
                    self.in_air = True
                    self.flying = True
                else:
                    raise AssertionError("unexpected vertical locomotion press count")
            elif first["x"] > 500:
                self.orientation_y += 15.0
            else:
                self.position_z -= 1.0
            return None
        if method == "POST" and path.endswith("/element"):
            self.last_identifier = body["value"]
            return {"element-6066-11e4-a52e-4f735466cecf": "element-1"}
        if method == "POST" and path.endswith("/element/element-1/click"):
            if self.last_identifier == "OverteTabletOpen":
                self.tablet_open = True
            elif self.last_identifier == "OverteTabletClose":
                self.tablet_open = False
            return None
        if method == "DELETE" and path.endswith("/actions"):
            return None
        if method == "DELETE" and path.startswith("/session/"):
            return None
        if method == "GET" and path.startswith("/session/"):
            return {"sessionId": "fake-session"}
        raise AssertionError(f"unexpected WebDriver call: {method} {path}")


class AppiumAdapterTests(unittest.TestCase):
    def test_ios_runtime_revision_matches_the_toolchain_lock(self) -> None:
        lock = json.loads(
            (DEVICE_ROOT / "ios" / "toolchain.lock.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            lock["serviceRuntimeRevision"],
            APPIUM.AppiumAdapter.IOS_SERVICE_RUNTIME_REVISION,
        )

    def test_session_creation_has_a_bounded_physical_wda_start_timeout(self) -> None:
        response = mock.MagicMock()
        response.headers = {}
        response.read.return_value = json.dumps({
            "value": {"sessionId": "fake-session"},
        }).encode("utf-8")
        response.__enter__.return_value = response
        with mock.patch.object(APPIUM, "urlopen", return_value=response) as request:
            value = APPIUM.WebDriver("http://127.0.0.1:4723").call(
                "POST", "/session", {})
        self.assertEqual({"sessionId": "fake-session"}, value)
        self.assertEqual(
            APPIUM.WebDriver.SESSION_START_TIMEOUT_SECONDS,
            request.call_args.kwargs["timeout"],
        )
        self.assertLessEqual(APPIUM.WebDriver.SESSION_START_TIMEOUT_SECONDS, 180)

    def test_regular_commands_keep_the_short_timeout(self) -> None:
        response = mock.MagicMock()
        response.headers = {}
        response.read.return_value = b'{"value":{}}'
        response.__enter__.return_value = response
        with mock.patch.object(APPIUM, "urlopen", return_value=response) as request:
            APPIUM.WebDriver("http://127.0.0.1:4723").call(
                "GET", "/session/fake-session")
        self.assertEqual(
            APPIUM.WebDriver.COMMAND_TIMEOUT_SECONDS,
            request.call_args.kwargs["timeout"],
        )

    def test_http_error_classifies_wda_launch_without_leaking_response(self) -> None:
        private_identifier = "00000000-1111-2222-3333-444444444444"
        body = json.dumps({
            "value": {
                "error": "unknown error",
                "message": (
                    "Unable to launch WebDriverAgent. Make sure application "
                    f"com.private.wda.{private_identifier} exists and it is launchable."
                ),
            },
        }).encode("utf-8")
        error = HTTPError(
            "http://127.0.0.1:4723/session", 500, "error", {}, io.BytesIO(body))
        with mock.patch.object(APPIUM, "urlopen", side_effect=error):
            with self.assertRaisesRegex(
                    RuntimeError,
                    r"HTTP 500 \(the preinstalled WebDriverAgent could not be launched\)") as raised:
                APPIUM.WebDriver("http://127.0.0.1:4723").call("POST", "/session", {})
        self.assertNotIn(private_identifier, str(raised.exception))
        self.assertNotIn("com.private", str(raised.exception))

    def test_http_error_does_not_echo_unclassified_response(self) -> None:
        private_value = "private-device-and-capability-value"
        body = json.dumps({
            "value": {"error": "unknown error", "message": private_value},
        }).encode("utf-8")
        error = HTTPError(
            "http://127.0.0.1:4723/session", 500, "error", {}, io.BytesIO(body))
        with mock.patch.object(APPIUM, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, r"Appium request failed with HTTP 500") \
                    as raised:
                APPIUM.WebDriver("http://127.0.0.1:4723").call("POST", "/session", {})
        self.assertNotIn(private_value, str(raised.exception))

    def test_http_error_classifies_wda_background_10300_without_private_values(self) -> None:
        private_identifier = "com.private.wda.00000000-1111-2222-3333-444444444444"
        body = json.dumps({
            "value": {
                "error": "unknown error",
                "message": (
                    "Error Domain=XCTestErrorDomain Code=10300 Failed to background "
                    f"test runner within 30.0s. Runner={private_identifier}"
                ),
            },
        }).encode("utf-8")
        error = HTTPError(
            "http://127.0.0.1:4723/session", 500, "error", {}, io.BytesIO(body))
        with mock.patch.object(APPIUM, "urlopen", side_effect=error):
            with self.assertRaisesRegex(
                    RuntimeError,
                    r"HTTP 500 \(the preinstalled WebDriverAgent runner could not enter "
                    r"the background\)") as raised:
                APPIUM.WebDriver("http://127.0.0.1:4723").call("POST", "/session", {})
        self.assertNotIn(private_identifier, str(raised.exception))

    def adapter_and_session(self) -> tuple[object, FakeXCUITest, dict, dict]:
        target = ios_target()
        client = FakeXCUITest()
        state = {"sessionId": "fake-session", "generation": 1,
                 "targetFingerprint": "test"}
        adapter = APPIUM.AppiumAdapter.__new__(APPIUM.AppiumAdapter)
        adapter.platform = "ios"
        adapter.adapter_id = "appium-ios"
        adapter.IOS_LAUNCH_STABILITY_SECONDS = 0
        adapter.targets = {"private-ipad": target}
        adapter.ensure_session = lambda _selector: (client, "fake-session", state)
        adapter.save_session = lambda _selector, _value: None
        return adapter, client, state, target

    def test_full_ios_baseline_uses_one_launch_one_pid_and_documents_probe(self) -> None:
        adapter, client, state, target = self.adapter_and_session()
        scene_url = target["testBuild"]["fixtureOrigin"] + target["testBuild"]["scenePath"]
        description = adapter.describe("private-ipad")
        self.assertNotIn("model", description)
        self.assertNotIn("osVersion", description)

        adapter.invoke("private-ipad", "app.launch", {})
        self.assertEqual("4123", state["processIdentity"])
        identity = adapter.invoke("private-ipad", "app.process", {})["identity"]
        adapter.invoke("private-ipad", "scene.load", {"url": scene_url})
        ready = adapter.invoke("private-ipad", "probe.snapshot", {})
        before_look = ready["view"]["orientation"]["y"]
        adapter.invoke("private-ipad", "input.look", {"horizontal": 0.25, "vertical": 0.0})
        looked = adapter.invoke("private-ipad", "probe.snapshot", {})
        before_move = looked["avatar"]["position"]["z"]
        adapter.invoke("private-ipad", "input.move",
                       {"direction": "forward", "durationSeconds": 1.5})
        moved = adapter.invoke("private-ipad", "probe.snapshot", {})
        adapter.invoke("private-ipad", "tablet.open", {})
        opened = adapter.invoke("private-ipad", "probe.snapshot", {})
        adapter.invoke("private-ipad", "tablet.close", {})
        closed = adapter.invoke("private-ipad", "probe.snapshot", {})

        launches = [event for event in client.events
                    if event[:2] == ("execute", "mobile: launchApp")]
        self.assertEqual(1, len(launches))
        launch_index = client.events.index(launches[0])
        self.assertEqual(
            ["mobile: queryAppState", "mobile: activeAppInfo"],
            [event[1] for event in client.events[launch_index + 1:launch_index + 3]],
        )
        self.assertFalse(any(event[:2] == ("execute", "mobile: activateApp")
                             for event in client.events))
        self.assertEqual([
            "--no-updater", "--url", scene_url,
            "--testScript", "http://lab.example:18080/overte_e2e_probe.js",
            "--testResultsLocation", "overte-e2e",
        ], launches[0][2]["arguments"])
        pulls = [event[2]["remotePath"] for event in client.events
                 if event[:2] == ("execute", "mobile: pullFile")]
        self.assertTrue(pulls)
        self.assertEqual({"@org.overte.e2e:documents/overte-e2e/overte-probe.json"},
                         set(pulls))
        self.assertEqual("4123", identity)
        self.assertNotIn("lifecycle.background",
                         adapter.advertised_capabilities(target))
        self.assertEqual(identity,
                         adapter.invoke("private-ipad", "app.process", {})["identity"])
        self.assertGreater(looked["view"]["orientation"]["y"], before_look)
        self.assertLess(moved["avatar"]["position"]["z"], before_move)
        self.assertIs(opened["tablet"]["open"], True)
        self.assertIs(closed["tablet"]["open"], False)
        self.assertTrue(state["iosE2ELaunchCompleted"])

    def test_ios_launch_rejects_an_app_that_immediately_leaves_foreground(self) -> None:
        for observed_state in (1, 3):
            with self.subTest(observed_state=observed_state):
                adapter, client, state, _target = self.adapter_and_session()
                client.launch_state = observed_state

                with self.assertRaisesRegex(
                        RuntimeError, "iOS application is not foregrounded"):
                    adapter.invoke("private-ipad", "app.launch", {})

                self.assertEqual(1, len([
                    event for event in client.events
                    if event[:2] == ("execute", "mobile: launchApp")
                ]))
                self.assertFalse(any(
                    event[:2] == ("execute", "mobile: activeAppInfo")
                    for event in client.events
                ))
                self.assertNotIn("processIdentity", state)
                self.assertNotIn("iosE2ELaunchCompleted", state)
                self.assertNotIn("iosE2ESceneUrl", state)

    def test_ios_launch_rejects_invalid_active_application_identity(self) -> None:
        invalid_identities = (
            ("org.overte.some-other-app", 4123),
            ("org.overte.e2e", 0),
            ("org.overte.e2e", True),
            ("org.overte.e2e", "4123"),
        )
        for bundle, pid in invalid_identities:
            with self.subTest(bundle=bundle, pid=pid):
                adapter, client, state, _target = self.adapter_and_session()
                client.bundle = bundle
                client.pid = pid

                with self.assertRaisesRegex(
                        RuntimeError, "did not identify the configured application"):
                    adapter.invoke("private-ipad", "app.launch", {})

                self.assertEqual(1, len([
                    event for event in client.events
                    if event[:2] == ("execute", "mobile: launchApp")
                ]))
                self.assertNotIn("processIdentity", state)
                self.assertNotIn("iosE2ELaunchCompleted", state)
                self.assertNotIn("iosE2ESceneUrl", state)

    def test_ios_launch_rejects_a_delayed_flash_crash_before_success_marker(self) -> None:
        adapter, client, state, _target = self.adapter_and_session()
        adapter.IOS_LAUNCH_STABILITY_SECONDS = 1.0

        def exit_during_stability_window(_seconds: float) -> None:
            client.app_state = 1

        with mock.patch.object(
                APPIUM.time, "sleep", side_effect=exit_during_stability_window) as delay, \
                self.assertRaisesRegex(
                    RuntimeError, "iOS application is not foregrounded"):
            adapter.invoke("private-ipad", "app.launch", {})

        delay.assert_called_once_with(1.0)
        self.assertEqual(1, len([
            event for event in client.events
            if event[:2] == ("execute", "mobile: launchApp")
        ]))
        self.assertEqual("4123", state["processIdentity"])
        self.assertNotIn("iosE2ELaunchCompleted", state)
        self.assertNotIn("iosE2ESceneUrl", state)
    def test_ios_sound_capability_is_exactly_gated(self) -> None:
        adapter, _client, _state, target = self.adapter_and_session()
        advertised = adapter.advertised_capabilities(target)
        self.assertIn("sound.play", advertised)
        self.assertNotIn("navigation.enter-domain", advertised)
        self.assertNotIn("asset.load", advertised)
        for mutation in (
                lambda value: value.pop("soundControl"),
                lambda value: value["soundControl"].__setitem__("commandPath", "/other.json"),
                lambda value: value.pop("testBuild"),
                lambda value: value.__setitem__("probe", {})):
            candidate = ios_target()
            mutation(candidate)
            self.assertNotIn("sound.play", adapter.advertised_capabilities(candidate))

    def test_ios_sound_posts_exact_payload_and_preserves_pid(self) -> None:
        adapter, client, state, target = self.adapter_and_session()
        adapter.invoke("private-ipad", "app.launch", {})
        identity = adapter.invoke("private-ipad", "app.process", {})["identity"]
        payload = {"schemaVersion": 1, "commandId": "ios-sound-1", "action": "play",
                   "soundUrl": "http://lab.example:18080/sound.wav?requestId=one"}
        response = mock.MagicMock(status=200)
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        arguments = {"schemaVersion": 1, "commandId": "ios-sound-1",
                     "url": payload["soundUrl"],
                     "commandUrl": "http://lab.example:18080/sound-command.json"}
        with mock.patch.object(APPIUM, "urlopen", return_value=response) as post:
            result = adapter.invoke("private-ipad", "sound.play", arguments)
        self.assertEqual({"requested": True, "commandId": "ios-sound-1"}, result)
        request = post.call_args.args[0]
        self.assertEqual(arguments["commandUrl"], request.full_url)
        self.assertEqual(payload, json.loads(request.data))
        self.assertEqual(5, post.call_args.kwargs["timeout"])
        self.assertEqual(identity, state["processIdentity"])
        self.assertEqual(1, len([event for event in client.events
                                if event[:2] == ("execute", "mobile: launchApp")]))

    def test_ios_sound_rejects_invalid_or_missing_channel_before_post(self) -> None:
        adapter, _client, _state, target = self.adapter_and_session()
        adapter.invoke("private-ipad", "app.launch", {})
        base = {"schemaVersion": 1, "commandId": "ios-sound-2",
                "url": "http://lab.example:18080/sound.wav",
                "commandUrl": "http://lab.example:18080/sound-command.json"}
        for invalid in (base | {"url": "file:///private/sound.wav"},
                        base | {"commandUrl": "http://other.example/sound-command.json"},
                        base | {"commandUrl": "http://lab.example:18080/other.json"}):
            with self.subTest(invalid=invalid), \
                    self.assertRaisesRegex(RuntimeError, "sound.play"):
                adapter.invoke("private-ipad", "sound.play", invalid)
        target.pop("soundControl")
        with mock.patch.object(APPIUM, "urlopen") as post, \
                self.assertRaisesRegex(RuntimeError, "controlled fixture sound channel"):
            adapter.invoke("private-ipad", "sound.play", base)
        post.assert_not_called()

    def test_ios_sound_detects_webdriver_failure_and_process_restart(self) -> None:
        adapter, client, _state, _target = self.adapter_and_session()
        adapter.invoke("private-ipad", "app.launch", {})
        arguments = {"schemaVersion": 1, "commandId": "ios-sound-3",
                     "url": "http://lab.example:18080/sound.wav",
                     "commandUrl": "http://lab.example:18080/sound-command.json"}
        original_execute = client.execute
        client.execute = mock.Mock(side_effect=RuntimeError("Appium rejected command"))
        with mock.patch.object(APPIUM, "urlopen") as post, \
                self.assertRaisesRegex(RuntimeError, "Appium rejected command"):
            adapter.invoke("private-ipad", "sound.play", arguments)
        post.assert_not_called()
        client.execute = original_execute

        payload = {"schemaVersion": 1, "commandId": "ios-sound-3", "action": "play",
                   "soundUrl": arguments["url"]}
        response = mock.MagicMock(status=200)
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response

        def restart_after_post(_request, **_kwargs):
            client.pid += 1
            return response

        with mock.patch.object(APPIUM, "urlopen", side_effect=restart_after_post), \
                self.assertRaisesRegex(RuntimeError, "process restarted"):
            adapter.invoke("private-ipad", "sound.play", arguments)

    def test_ios_jump_and_flight_use_the_real_virtual_pad_in_one_process(self) -> None:
        adapter, client, state, target = self.adapter_and_session()
        adapter.invoke("private-ipad", "app.launch", {})
        identity = adapter.invoke("private-ipad", "app.process", {})["identity"]

        advertised = adapter.advertised_capabilities(target)
        self.assertIn("input.jump", advertised)
        self.assertIn("input.fly", advertised)

        self.assertEqual(
            {"performed": True},
            adapter.invoke("private-ipad", "input.jump", {}))
        airborne = adapter.invoke("private-ipad", "probe.snapshot", {})
        landed = adapter.invoke("private-ipad", "probe.snapshot", {})
        self.assertIs(airborne["avatar"]["inAir"], True)
        self.assertIs(airborne["avatar"]["flying"], False)
        self.assertGreater(airborne["avatar"]["position"]["y"], 2.0)
        self.assertIs(landed["avatar"]["inAir"], False)
        self.assertEqual(2.0, landed["avatar"]["position"]["y"])

        self.assertEqual(
            {"performed": True},
            adapter.invoke("private-ipad", "input.fly", {"durationSeconds": 3.0}))
        flying = adapter.invoke("private-ipad", "probe.snapshot", {})
        self.assertIs(flying["avatar"]["inAir"], True)
        self.assertIs(flying["avatar"]["flying"], True)
        self.assertGreaterEqual(flying["avatar"]["position"]["y"], 4.0)

        vertical_actions = [event[2]["actions"][0]["actions"]
                            for event in client.events
                            if event[0] == "POST" and event[1].endswith("/actions")
                            and event[2]["actions"][0]["id"]
                            == "overte-ios-vertical-locomotion"]
        self.assertEqual(2, len(vertical_actions))
        self.assertEqual([1, 2], [
            sum(1 for action in actions if action["type"] == "pointerDown")
            for actions in vertical_actions
        ])
        flight_pauses = [action["duration"] for action in vertical_actions[1]
                         if action["type"] == "pause"]
        self.assertEqual([100, 250, 3000], flight_pauses)
        self.assertEqual(identity, state["processIdentity"])
        self.assertEqual(identity,
                         adapter.invoke("private-ipad", "app.process", {})["identity"])
        self.assertEqual(1, len([event for event in client.events
                                if event[:2] == ("execute", "mobile: launchApp")]))

    def test_ios_vertical_locomotion_rejects_ambiguous_controls_and_arguments(self) -> None:
        adapter, client, _state, target = self.adapter_and_session()
        adapter.invoke("private-ipad", "app.launch", {})
        actions_before = len([event for event in client.events
                              if event[0] == "POST" and event[1].endswith("/actions")])

        with self.assertRaisesRegex(RuntimeError, "does not accept arguments"):
            adapter.invoke("private-ipad", "input.jump", {"durationSeconds": 1.0})
        for values in ({}, {"durationSeconds": 0.09}, {"durationSeconds": 10.01},
                       {"durationSeconds": 3.0, "direction": "up"}):
            with self.subTest(values=values):
                with self.assertRaisesRegex(RuntimeError, "durationSeconds"):
                    adapter.invoke("private-ipad", "input.fly", values)
        actions_after = len([event for event in client.events
                             if event[0] == "POST" and event[1].endswith("/actions")])
        self.assertEqual(actions_before, actions_after)

        invalid = dict(target["controls"]["verticalLocomotion"])
        invalid["fallbackPoint"] = [0.5, 0.5]
        with self.assertRaisesRegex(RuntimeError, "exact audited control fields"):
            adapter.validate_ios_vertical_locomotion(invalid)

    def test_ios_vertical_locomotion_releases_actions_after_appium_failure(self) -> None:
        adapter, client, _state, _target = self.adapter_and_session()
        adapter.invoke("private-ipad", "app.launch", {})
        original_call = client.call

        def fail_touch(method: str, path: str, payload: dict | None = None) -> object:
            if method == "POST" and path.endswith("/actions"):
                client.events.append((method, path, payload or {}))
                raise RuntimeError("Appium touch failed")
            return original_call(method, path, payload)

        client.call = mock.Mock(side_effect=fail_touch)
        with self.assertRaisesRegex(RuntimeError, "Appium touch failed"):
            adapter.invoke("private-ipad", "input.jump", {})
        self.assertTrue(any(call.args[:2]
                            == ("DELETE", "/session/fake-session/actions")
                            for call in client.call.call_args_list))

    def test_common_vertical_session_runs_through_ios_appium_contract(self) -> None:
        adapter, client, state, _target = self.adapter_and_session()
        adapter.invoke("private-ipad", "app.launch", {})
        identity = adapter.invoke("private-ipad", "app.process", {})["identity"]

        support = types.ModuleType("module_support")

        class InfrastructureError(RuntimeError):
            pass

        def operation(name: str, arguments: dict | None = None) -> dict:
            return adapter.invoke("private-ipad", name, arguments or {})

        def fail(message: str) -> None:
            raise RuntimeError(message)

        support.InfrastructureError = InfrastructureError
        support.fail = fail
        support.operation = operation
        support.write_json = lambda _name, _value: None
        support.process_identity = lambda: identity
        support.assert_process = lambda expected, _label: self.assertEqual(identity, expected)
        support.assert_foreground = lambda _label: None
        common_spec = importlib.util.spec_from_file_location(
            "overte_ios_common_vertical_session", DEVICE_ROOT / "overte_session.py")
        assert common_spec and common_spec.loader
        common = importlib.util.module_from_spec(common_spec)
        with mock.patch.dict(sys.modules, {"module_support": support}), \
                mock.patch.dict(os.environ, {
                    "OVERTE_E2E_POLL_SECONDS": "0.05",
                    "OVERTE_E2E_TIMEOUT_SECONDS": "1",
                }):
            common_spec.loader.exec_module(common)
            session = common.OverteSession()
            jump_before, airborne, landed = session.jump()
            fly_before, flying = session.fly(duration_seconds=2.0)

        self.assertGreater(airborne["avatar"]["position"]["y"],
                           jump_before["avatar"]["position"]["y"])
        self.assertFalse(landed["avatar"]["inAir"])
        self.assertGreater(flying["avatar"]["position"]["y"],
                           fly_before["avatar"]["position"]["y"])
        self.assertTrue(flying["avatar"]["flying"])
        self.assertEqual(identity, state["processIdentity"])
        self.assertEqual(1, len([event for event in client.events
                                if event[:2] == ("execute", "mobile: launchApp")]))

    def test_pid_change_aborts_before_next_behavioral_gesture(self) -> None:
        adapter, client, _state, _target = self.adapter_and_session()
        adapter.invoke("private-ipad", "app.launch", {})
        adapter.invoke("private-ipad", "app.process", {})
        actions_before = len([item for item in client.events if item[1].endswith("/actions")])
        client.pid += 1
        with self.assertRaisesRegex(RuntimeError, r"^ASSERTION: .*process restarted"):
            adapter.invoke("private-ipad", "input.look", {})
        actions_after = len([item for item in client.events if item[1].endswith("/actions")])
        self.assertEqual(actions_before, actions_after)

        client.pid -= 1
        client.app_state = 3
        with self.assertRaisesRegex(RuntimeError, r"^ASSERTION: .*outside the foreground"):
            adapter.invoke("private-ipad", "app.process", {})

    def test_accessibility_audit_can_observe_open_then_close_identifier_in_one_session(self) -> None:
        adapter, client, _state, target = self.adapter_and_session()
        scene_url = target["testBuild"]["fixtureOrigin"] + target["testBuild"]["scenePath"]
        adapter.invoke("private-ipad", "app.launch", {})
        adapter.invoke("private-ipad", "scene.load", {"url": scene_url})
        closed = adapter.invoke("private-ipad", "accessibility.snapshot", {})["source"]
        self.assertIn("OverteTabletOpen", closed)
        self.assertNotIn("OverteTabletClose", closed)
        adapter.invoke("private-ipad", "tablet.open", {})
        opened = adapter.invoke("private-ipad", "accessibility.snapshot", {})["source"]
        self.assertIn("OverteTabletClose", opened)
        self.assertNotIn("OverteTabletOpen", opened)
        adapter.invoke("private-ipad", "tablet.close", {})
        self.assertIs(adapter.invoke(
            "private-ipad", "probe.snapshot", {})["tablet"]["open"], False)
        launches = [event for event in client.events
                    if event[:2] == ("execute", "mobile: launchApp")]
        self.assertEqual(1, len(launches))

    def test_probe_requires_current_schema_and_fresh_sample(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "stale"):
            APPIUM.AppiumAdapter.validate_probe(
                snapshot(sampled=int(time.time() * 1000) - 60_000))
        invalid = snapshot()
        invalid.pop("tablet")
        with self.assertRaisesRegex(RuntimeError, "object field tablet"):
            APPIUM.AppiumAdapter.validate_probe(invalid)

    def test_prebuilt_wda_tree_accepts_real_parent_and_rejects_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="overte-wda-parent-") as name:
            private = Path(name)
            real_parent = private / "real"
            real_parent.mkdir(mode=0o700)
            application = prebuilt_wda(real_parent)
            digest = APPIUM.AppiumAdapter._private_tree_sha256(
                application, "test WDA")
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

            linked_parent = private / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(
                    RuntimeError, "safe current-user-owned private tree"):
                APPIUM.AppiumAdapter._private_tree_sha256(
                    linked_parent / application.name, "test WDA")

    def test_physical_attestation_rejects_private_identity_mismatch(self) -> None:
        for observed in ("different-test-device", None):
            with self.subTest(observed=observed):
                adapter, client, _state, target = self.adapter_and_session()
                device_info = {"isSimulator": False, "productVersion": "18.6"}
                if observed is not None:
                    device_info["udid"] = observed
                client.execute = mock.Mock(return_value=device_info)
                with self.assertRaisesRegex(RuntimeError, "device identity"):
                    adapter.attest_physical_target(client, "fake-session", target)
                self.assertEqual(mock.call("fake-session", "mobile: deviceInfo"),
                                 client.execute.call_args_list[-1])

    def test_immutable_pre_session_helper_keeps_device_identity_out_of_argv_and_output(self) -> None:
        adapter, _client, _state, target = self.adapter_and_session()
        target["_receiptWdaBundleId"] = "org.overte.WebDriverAgentRunner.xctrunner"
        completed = mock.Mock(returncode=0, stdout="PASS\n", stderr="")
        with mock.patch.object(adapter, "immutable_ios_runtime_wrapper",
                               return_value=Path("/immutable/remotexpc_tunnel.py")), \
                mock.patch.object(APPIUM.subprocess, "run", return_value=completed) as execute:
            adapter.pre_session_device_attestation(target)
        arguments = execute.call_args.args[0]
        self.assertEqual(["/immutable/remotexpc_tunnel.py", "device-preflight"], arguments)
        self.assertNotIn("private-device-id", " ".join(arguments))
        self.assertEqual({
            "udid": "private-device-id",
            "overteBundleId": target["appId"],
            "wdaBundleId": "org.overte.WebDriverAgentRunner.xctrunner",
        },
                         json.loads(execute.call_args.kwargs["input"]))

        completed.returncode = 2
        completed.stderr = "private-device-id"
        with mock.patch.object(adapter, "immutable_ios_runtime_wrapper",
                               return_value=Path("/immutable/remotexpc_tunnel.py")), \
                mock.patch.object(APPIUM.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "private device preflight") as raised:
                adapter.pre_session_device_attestation(target)
        self.assertNotIn("private-device-id", str(raised.exception))

    def test_ios_session_bootstrap_is_strictly_limited_to_ios26_personal_team(self) -> None:
        target = ios_target()
        target.update({
            "artifactMode": "personal-team-preinstalled",
            "iosSessionBootstrap": {"backgroundWdaRunner": True},
        })
        target["capabilities"]["appium:platformVersion"] = "26.0"
        APPIUM.AppiumAdapter.validate_ios_session_bootstrap(target)

        invalid_mutations = (
            lambda value: value.update(platform="android"),
            lambda value: value.update(physical=False),
            lambda value: value.update(artifactMode="signed-ipa"),
            lambda value: value["capabilities"].update(
                {"appium:usePreinstalledWDA": False}),
            lambda value: value["capabilities"].update(
                {"appium:platformVersion": "25.9"}),
            lambda value: value.update(
                iosSessionBootstrap={"backgroundWdaRunner": True, "retry": True}),
            lambda value: value.update(
                iosSessionBootstrap={"backgroundWdaRunner": False}),
            lambda value: value.update(
                iosSessionBootstrap={"backgroundWdaRunner": 1}),
        )
        for mutate in invalid_mutations:
            with self.subTest(mutation=mutate):
                invalid = json.loads(json.dumps(target))
                mutate(invalid)
                with self.assertRaisesRegex(RuntimeError, "iosSessionBootstrap|bootstrap"):
                    APPIUM.AppiumAdapter.validate_ios_session_bootstrap(invalid)

    def test_ios_session_bootstrap_runs_parallel_to_exactly_one_session_post(self) -> None:
        adapter, client, _state, target = self.adapter_and_session()
        del adapter.ensure_session
        target.update({
            "artifactMode": "personal-team-preinstalled",
            "_artifactMode": "personal-team-preinstalled",
            "_receiptWdaBundleId": "com.private.wda.runner",
            "iosSessionBootstrap": {"backgroundWdaRunner": True},
        })
        target["capabilities"]["appium:platformVersion"] = "26.0"
        adapter.read_session = lambda _selector: None
        adapter.validate_ios_artifact_receipt = lambda _target, hash_files=False: None
        adapter.install_receipt_bound_ios_apps = mock.Mock()
        adapter.pre_session_device_attestation = mock.Mock()
        adapter.attest_physical_target = mock.Mock()
        adapter.save_session = mock.Mock()

        events: list[str] = []
        input_pipe = mock.Mock()
        input_pipe.close.side_effect = lambda: events.append("stdin-closed")
        output_pipe = mock.Mock()
        output_pipe.fileno.return_value = 73
        process = mock.Mock(returncode=0, stdin=input_pipe, stdout=output_pipe)

        def communicate(*, timeout: int) -> tuple[str, str]:
            self.assertEqual(
                APPIUM.AppiumAdapter.IOS_SESSION_BOOTSTRAP_JOIN_TIMEOUT_SECONDS,
                timeout,
            )
            events.append("helper-joined")
            return "PASS\n", ""

        process.communicate.side_effect = communicate

        def start_helper(*args, **kwargs):
            events.append("helper-started")
            return process

        def appium_call(method: str, path: str, payload: dict | None = None) -> object:
            events.append(f"{method} {path}")
            if method == "POST" and path == "/session":
                self.assertIn("stdin-closed", events)
                self.assertNotIn("helper-joined", events)
                return {"sessionId": "new-session"}
            raise AssertionError(f"unexpected WebDriver call: {method} {path}")

        client.call = mock.Mock(side_effect=appium_call)
        with mock.patch.object(APPIUM, "WebDriver", return_value=client), \
                mock.patch.object(adapter, "immutable_ios_runtime_wrapper",
                                  return_value=Path("/immutable/remotexpc_tunnel.py")), \
                mock.patch.dict(os.environ, {
                    "OVERTE_IOS_SESSION_BOOTSTRAP_HELPER": "/usr/bin/bash",
                }), \
                mock.patch.object(APPIUM.select, "select",
                                  return_value=([73], [], [])), \
                mock.patch.object(APPIUM.os, "read", side_effect=lambda _fd, _limit: (
                    events.append("helper-ready") or b"READY\n")), \
                mock.patch.object(APPIUM.subprocess, "Popen",
                                  side_effect=start_helper) as popen:
            _client, session, _saved = adapter.ensure_session("private-ipad")

        self.assertEqual("new-session", session)
        self.assertEqual(
            ["helper-started", "stdin-closed", "helper-ready",
             "POST /session", "helper-joined"],
            events,
        )
        self.assertEqual(1, sum(
            call.args[:2] == ("POST", "/session") for call in client.call.call_args_list))
        argv = popen.call_args.args[0]
        self.assertEqual([
            "/immutable/remotexpc_tunnel.py", "wda-session-bootstrap",
            "--service-runtime", "/immutable",
        ], argv)
        self.assertNotIn("private-device-id", " ".join(argv))
        self.assertNotIn("com.private.wda.runner", " ".join(argv))
        self.assertIs(popen.call_args.kwargs["start_new_session"], True)
        expected_request = json.dumps({
            "schemaVersion": 1,
            "udid": "private-device-id",
            "wdaBundleId": "com.private.wda.runner",
        }, separators=(",", ":")) + "\n"
        input_pipe.write.assert_called_once_with(expected_request)
        input_pipe.flush.assert_called_once_with()
        input_pipe.close.assert_called_once_with()

    def test_ios_session_bootstrap_is_reaped_when_session_post_fails(self) -> None:
        adapter, client, _state, target = self.adapter_and_session()
        target.update({
            "artifactMode": "personal-team-preinstalled",
            "_artifactMode": "personal-team-preinstalled",
            "_receiptWdaBundleId": "com.private.wda.runner",
            "iosSessionBootstrap": {"backgroundWdaRunner": True},
        })
        target["capabilities"]["appium:platformVersion"] = "26.0"
        input_pipe = mock.Mock()
        output_pipe = mock.Mock()
        output_pipe.fileno.return_value = 73
        process = mock.Mock(returncode=0, stdin=input_pipe, stdout=output_pipe)
        process.communicate.return_value = ("PASS\n", "")
        client.call = mock.Mock(side_effect=RuntimeError("redacted Appium failure"))
        with mock.patch.object(adapter, "immutable_ios_runtime_wrapper",
                               return_value=Path("/immutable/remotexpc_tunnel.py")), \
                mock.patch.object(APPIUM.select, "select",
                                  return_value=([73], [], [])), \
                mock.patch.object(APPIUM.os, "read", return_value=b"READY\n"), \
                mock.patch.object(APPIUM.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "redacted Appium failure"):
                adapter.create_appium_session(client, target)
        self.assertEqual(1, client.call.call_count)
        self.assertEqual(("POST", "/session"), client.call.call_args.args[:2])
        process.communicate.assert_called_once_with(
            timeout=APPIUM.AppiumAdapter.IOS_SESSION_BOOTSTRAP_JOIN_TIMEOUT_SECONDS)

    def test_ios_session_bootstrap_timeout_terminates_and_reaps_without_output(self) -> None:
        private_value = "private-device-id"
        process = mock.Mock(returncode=None, stdin=None, pid=424242)
        process.poll.return_value = None
        process.communicate.side_effect = [
            APPIUM.subprocess.TimeoutExpired("private-helper", 45,
                                             output=private_value, stderr=private_value),
            APPIUM.subprocess.TimeoutExpired("private-helper", 5,
                                             output=private_value, stderr=private_value),
            (private_value, private_value),
        ]
        with mock.patch.object(APPIUM.os, "killpg") as kill_group:
            with self.assertRaisesRegex(RuntimeError, "bounded runtime") as raised:
                APPIUM.AppiumAdapter.finish_ios_session_bootstrap(process)
        self.assertEqual([
            mock.call(424242, APPIUM.signal.SIGTERM),
            mock.call(424242, APPIUM.signal.SIGKILL),
        ], kill_group.call_args_list)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        self.assertEqual(3, process.communicate.call_count)
        self.assertNotIn(private_value, str(raised.exception))

    def test_ios_session_bootstrap_cleans_group_after_wrapper_already_exited(self) -> None:
        process = mock.Mock(returncode=2, pid=424244)
        process.poll.return_value = 2
        process.communicate.return_value = ("", "")
        with mock.patch.object(APPIUM.os, "killpg") as kill_group:
            APPIUM.AppiumAdapter._stop_ios_session_bootstrap(process)
        kill_group.assert_called_once_with(424244, APPIUM.signal.SIGTERM)
        process.communicate.assert_called_once_with(
            timeout=APPIUM.AppiumAdapter.IOS_SESSION_BOOTSTRAP_STOP_TIMEOUT_SECONDS)

    def test_ios_session_bootstrap_rejects_non_generic_completion_output(self) -> None:
        private_value = "PASS:private-device-id\n"
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (private_value, "")
        with self.assertRaisesRegex(RuntimeError, "runner transition") as raised:
            APPIUM.AppiumAdapter.finish_ios_session_bootstrap(process)
        self.assertNotIn(private_value.strip(), str(raised.exception))

    def test_ios_session_bootstrap_requires_ready_before_any_session_post(self) -> None:
        adapter, client, _state, target = self.adapter_and_session()
        target.update({
            "artifactMode": "personal-team-preinstalled",
            "_artifactMode": "personal-team-preinstalled",
            "_receiptWdaBundleId": "com.private.wda.runner",
            "iosSessionBootstrap": {"backgroundWdaRunner": True},
        })
        target["capabilities"]["appium:platformVersion"] = "26.0"
        input_pipe = mock.Mock()
        output_pipe = mock.Mock()
        process = mock.Mock(returncode=None, stdin=input_pipe, stdout=output_pipe,
                            pid=434343)
        process.poll.return_value = None
        process.communicate.return_value = ("", "")
        client.call = mock.Mock()
        with mock.patch.object(adapter, "immutable_ios_runtime_wrapper",
                               return_value=Path("/immutable/remotexpc_tunnel.py")), \
                mock.patch.object(APPIUM.select, "select", return_value=([], [], [])), \
                mock.patch.object(APPIUM.os, "killpg") as kill_group, \
                mock.patch.object(APPIUM.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                adapter.create_appium_session(client, target)
        client.call.assert_not_called()
        kill_group.assert_called_once_with(434343, APPIUM.signal.SIGTERM)
        process.terminate.assert_not_called()
        process.communicate.assert_called_once_with(
            timeout=APPIUM.AppiumAdapter.IOS_SESSION_BOOTSTRAP_STOP_TIMEOUT_SECONDS)

    def test_ios_session_bootstrap_preserves_failed_session_for_later_cleanup(self) -> None:
        adapter, client, _state, target = self.adapter_and_session()
        target.update({
            "artifactMode": "personal-team-preinstalled",
            "_artifactMode": "personal-team-preinstalled",
            "_receiptWdaBundleId": "com.private.wda.runner",
            "iosSessionBootstrap": {"backgroundWdaRunner": True},
        })
        target["capabilities"]["appium:platformVersion"] = "26.0"
        process = mock.Mock(returncode=2)
        process.communicate.return_value = ("", "")
        client.call = mock.Mock(side_effect=[
            {"sessionId": "cleanup-session"},
            RuntimeError("redacted cleanup failure"),
        ])
        adapter.start_ios_session_bootstrap = mock.Mock(return_value=process)
        adapter.save_session = mock.Mock()

        with self.assertRaisesRegex(RuntimeError, "runner transition"):
            adapter.create_appium_session(client, target)

        self.assertEqual([
            mock.call("POST", "/session", mock.ANY),
            mock.call("DELETE", "/session/cleanup-session"),
        ], client.call.call_args_list)
        adapter.save_session.assert_called_once_with("private-ipad", {
            "sessionId": "cleanup-session",
            "generation": 0,
            "targetFingerprint": "bootstrap-cleanup-pending",
            "bootstrapCleanupPending": True,
        })

    def test_pending_bootstrap_session_is_deleted_before_new_session(self) -> None:
        adapter, client, _state, target = self.adapter_and_session()
        del adapter.ensure_session
        pending = {
            "sessionId": "cleanup-session",
            "generation": 0,
            "targetFingerprint": "bootstrap-cleanup-pending",
            "bootstrapCleanupPending": True,
        }
        adapter.read_session = mock.Mock(return_value=pending)
        adapter.state_path = mock.Mock()
        pending_path = mock.Mock()
        adapter.state_path.return_value = pending_path
        adapter.validate_ios_artifact_receipt = mock.Mock()
        adapter.install_receipt_bound_ios_apps = mock.Mock()
        adapter.pre_session_device_attestation = mock.Mock()
        adapter.create_appium_session = mock.Mock(
            return_value={"sessionId": "replacement-session"})
        adapter.attest_physical_target = mock.Mock()
        adapter.save_session = mock.Mock()
        client.call = mock.Mock(return_value=None)

        with mock.patch.object(APPIUM, "WebDriver", return_value=client):
            _client, session, _state = adapter.ensure_session("private-ipad")

        self.assertEqual("replacement-session", session)
        self.assertEqual(
            mock.call("DELETE", "/session/cleanup-session"),
            client.call.call_args_list[0],
        )
        pending_path.unlink.assert_called_once_with(missing_ok=True)

    def test_signed_mode_installs_receipt_pair_before_preflight_without_private_argv(self) -> None:
        adapter, _client, _state, target = self.adapter_and_session()
        target["_artifactMode"] = "signed-ipa"
        target["_artifactReceiptPath"] = "/private/run/receipt.json"
        completed = mock.Mock(returncode=0, stdout="PASS\n", stderr="")
        with mock.patch.object(adapter, "immutable_ios_runtime_wrapper",
                               return_value=Path("/immutable/remotexpc_tunnel.py")), \
                mock.patch.object(APPIUM.subprocess, "run", return_value=completed) as execute:
            # Replacement is unconditional for every new session, so a stale
            # same-version installation cannot make Appium silently reuse it.
            adapter.install_receipt_bound_ios_apps(target)
            adapter.install_receipt_bound_ios_apps(target)
        self.assertEqual(2, execute.call_count)
        for call in execute.call_args_list:
            arguments = call.args[0]
            self.assertEqual(
                ["/immutable/remotexpc_tunnel.py", "device-install"], arguments)
            self.assertNotIn("private-device-id", " ".join(arguments))
            self.assertEqual({
                "udid": "private-device-id", "receipt": "/private/run/receipt.json",
            }, json.loads(call.kwargs["input"]))

        target["_artifactMode"] = "personal-team-preinstalled"
        with mock.patch.object(APPIUM.subprocess, "run") as execute:
            adapter.install_receipt_bound_ios_apps(target)
        execute.assert_not_called()

    def test_session_write_does_not_follow_predictable_temporary_symlink(self) -> None:
        adapter, _client, _state, _target = self.adapter_and_session()
        with tempfile.TemporaryDirectory(prefix="overte-appium-session-") as name:
            directory = Path(name)
            victim = directory / "must-not-change"
            victim.write_text("private\n", encoding="utf-8")
            (directory / "session.tmp").symlink_to(victim)
            adapter.state_path = lambda _selector: directory / "session.json"
            adapter.save_session = APPIUM.AppiumAdapter.save_session.__get__(adapter)
            adapter.save_session("private-ipad", {"sessionId": "opaque"})
            self.assertEqual("private\n", victim.read_text(encoding="utf-8"))
            saved = directory / "session.json"
            self.assertEqual({"sessionId": "opaque"}, json.loads(saved.read_text()))
            self.assertEqual(0o600, saved.stat().st_mode & 0o777)

            saved.unlink()
            saved.symlink_to(victim)
            adapter.read_session = APPIUM.AppiumAdapter.read_session.__get__(adapter)
            with self.assertRaisesRegex(RuntimeError, "must not be a symbolic link"):
                adapter.read_session("private-ipad")

    def test_ios_contract_rejects_virtual_targets_and_coordinate_tablet_fallback(self) -> None:
        target = ios_target()
        target["controls"]["tablet"] = {"togglePoint": [0.5, 0.5]}
        with self.assertRaisesRegex(RuntimeError, "accessibility identifiers"):
            APPIUM.AppiumAdapter.validate_ios_test_build(target)

        config = {"schemaVersion": 1, "targets": [ios_target(enabled=False)]}
        config["targets"][0]["physical"] = False
        with tempfile.TemporaryDirectory(prefix="overte-appium-contract-") as name:
            path = Path(name) / "targets.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            path.chmod(0o600)
            with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": str(path)}):
                with self.assertRaisesRegex(RuntimeError, "physical device"):
                    APPIUM.AppiumAdapter("ios")

    def test_private_target_config_rejects_relative_symlink_and_public_mode(self) -> None:
        config = {"schemaVersion": 1, "targets": [ios_target(enabled=False)]}
        with tempfile.TemporaryDirectory(prefix="overte-appium-private-config-") as name:
            private = Path(name)
            path = private / "targets.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            path.chmod(0o644)
            with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": str(path)}):
                with self.assertRaisesRegex(RuntimeError, "mode 0600"):
                    APPIUM.AppiumAdapter("ios")
            path.chmod(0o600)
            link = private / "targets-link.json"
            link.symlink_to(path)
            with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": str(link)}):
                with self.assertRaisesRegex(RuntimeError, "symbolic links"):
                    APPIUM.AppiumAdapter("ios")
            with mock.patch.dict(os.environ, {"OVERTE_APPIUM_TARGETS": "targets.json"}):
                with self.assertRaisesRegex(RuntimeError, "absolute private path"):
                    APPIUM.AppiumAdapter("ios")

    @unittest.skipIf(APPIUM.sys.platform == "darwin", "Fedora-only loopback policy")
    def test_fedora_ios_rejects_remote_or_ambiguous_appium_server_url(self) -> None:
        for url in (
                "https://device-cloud.example/session", "http://localhost:4723",
                "http://127.0.0.1:4723/wd/hub", "http://user@127.0.0.1:4723"):
            with self.subTest(url=url):
                target = ios_target()
                target["serverUrl"] = url
                with self.assertRaisesRegex(RuntimeError, "bounded loopback URL"):
                    APPIUM.AppiumAdapter.validate_ios_host_strategy(target)

    @unittest.skipIf(APPIUM.sys.platform == "darwin", "Fedora-only WDA strategy")
    def test_enabled_fedora_target_cannot_bypass_receipt_bound_prebuilt_wda(self) -> None:
        target = ios_target()
        target["artifactReceipt"] = "/private/receipt.json"
        target["capabilities"].update({
            "appium:app": "/private/Overte.ipa",
            "appium:prebuiltWDAPath": "/private/WebDriverAgentRunner-Runner.app",
            "appium:webDriverAgentUrl": "http://127.0.0.1:8100",
        })
        with self.assertRaisesRegex(RuntimeError, "must not bypass"):
            APPIUM.AppiumAdapter.validate_ios_host_strategy(target)
        target["capabilities"].pop("appium:webDriverAgentUrl")
        APPIUM.AppiumAdapter.validate_ios_host_strategy(target)

    def test_receipt_binds_provenance_expiry_hashes_bundles_and_toolchain(self) -> None:
        target = ios_target()
        with tempfile.TemporaryDirectory(prefix="overte-ios-receipt-") as name:
            root = Path(name)
            overte = root / "Overte.ipa"
            wda = root / "WDA.ipa"
            wda_app = prebuilt_wda(root)
            overte.write_bytes(b"signed overte")
            wda.write_bytes(b"signed wda")
            overte.chmod(0o600)
            wda.chmod(0o600)
            target["capabilities"].update({
                "appium:app": str(overte),
                "appium:prebuiltWDAPath": str(wda_app),
            })
            now = datetime.now(timezone.utc)
            receipt = {
                "schemaVersion": 1,
                "contract": "overte-ios-fedora-e2e-receipt-v1",
                "sourceRevision": "a" * 40,
                "createdAt": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                "notAfter": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                "provenance": {
                    "repository": "overte-org/overte",
                    "repositoryId": 123,
                    "workflow": ".github/workflows/ios-bootstrap.yml",
                    "reusableWorkflow": ".github/workflows/ios-fedora-e2e-producer.yml",
                    "ref": "refs/heads/apple-ios",
                    "runId": 456,
                    "runAttempt": 1,
                },
                "overte": {"path": str(overte),
                           "sha256": APPIUM.AppiumAdapter._sha256_file(overte),
                           "bundleId": "org.overte.e2e"},
                "wda": {"ipaPath": str(wda),
                        "ipaSha256": APPIUM.AppiumAdapter._sha256_file(wda),
                        "prebuiltPath": str(wda_app),
                        "prebuiltTreeSha256": APPIUM.AppiumAdapter._private_tree_sha256(
                            wda_app, "test WDA"),
                        "bundleId": "org.overte.wda.xctrunner"},
                "toolchain": {"xcuitestDriver": "12.8.0", "remoteXpc": "5.15.3",
                              "webdriverAgent": "16.8.0"},
            }
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            receipt_path.chmod(0o600)
            target["artifactReceipt"] = str(receipt_path)
            APPIUM.AppiumAdapter.validate_ios_artifact_receipt(target, hash_files=True)

            receipt["provenance"]["runAttempt"] = 0
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "provenance"):
                APPIUM.AppiumAdapter.validate_ios_artifact_receipt(target, hash_files=True)

            receipt["provenance"]["runAttempt"] = 1
            (wda_app / "WebDriverAgentRunner-Runner").write_bytes(b"tampered")
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "tree SHA-256"):
                APPIUM.AppiumAdapter.validate_ios_artifact_receipt(target, hash_files=True)

            (wda_app / "WebDriverAgentRunner-Runner").write_bytes(
                b"private fake executable")
            linked_parent = root / "linked-private-parent"
            linked_parent.symlink_to(root, target_is_directory=True)
            linked_wda = linked_parent / wda_app.name
            receipt["wda"]["prebuiltPath"] = str(linked_wda)
            receipt["wda"]["prebuiltTreeSha256"] = \
                APPIUM.AppiumAdapter._private_tree_sha256(wda_app, "test WDA")
            target["capabilities"]["appium:prebuiltWDAPath"] = str(linked_wda)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "safe current-user-owned private tree"):
                APPIUM.AppiumAdapter.validate_ios_artifact_receipt(target, hash_files=True)

    def test_personal_team_receipt_requires_exact_manual_signing_provenance(self) -> None:
        target = ios_target()
        with tempfile.TemporaryDirectory(prefix="overte-personal-receipt-") as name:
            private = Path(name)
            overte = private / "Overte-PersonalTeam-E2E-signed.ipa"
            wda = private / "WebDriverAgentRunner-16.8.0-PersonalTeam-signed.ipa"
            wda_app = prebuilt_wda(private)
            overte.write_bytes(b"signed overte")
            wda.write_bytes(b"signed wda")
            now = datetime.now(timezone.utc)
            receipt = {
                "schemaVersion": 1,
                "contract": "overte-ios-personal-team-artifact-receipt-v1",
                "sourceRevision": "b" * 40,
                "createdAt": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                "notAfter": (now + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
                "provenance": {
                    "mode": "personal-team-manual-signing",
                    "unsignedKitContract": "overte-ios-personal-team-e2e-kit-v3",
                    "unsignedKitManifestSha256": "c" * 64,
                    "attestationContract": "overte-ios-personal-team-signed-handoff-v1",
                    "derivationBinding": "human-verified",
                },
                "overte": {
                    "path": str(overte),
                    "sha256": APPIUM.AppiumAdapter._sha256_file(overte),
                    "bundleId": target["appId"],
                },
                "wda": {
                    "ipaPath": str(wda),
                    "ipaSha256": APPIUM.AppiumAdapter._sha256_file(wda),
                    "prebuiltPath": str(wda_app),
                    "prebuiltTreeSha256": APPIUM.AppiumAdapter._private_tree_sha256(
                        wda_app, "test WDA"),
                    "bundleId": "org.overte.wda.xctrunner",
                },
                "toolchain": {
                    "xcuitestDriver": "12.8.0",
                    "remoteXpc": "5.15.3",
                    "webdriverAgent": "16.8.0",
                },
            }
            receipt_path = private / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            for path in (private, overte, wda, receipt_path):
                path.chmod(0o700 if path == private else 0o600)
            target["artifactReceipt"] = str(receipt_path)
            target["capabilities"].update({
                "appium:app": str(overte),
                "appium:prebuiltWDAPath": str(wda_app),
                "appium:updatedWDABundleId": "org.overte.wda",
            })
            APPIUM.AppiumAdapter.validate_ios_artifact_receipt(target, hash_files=True)
            receipt["provenance"]["derivationBinding"] = "unreviewed"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "provenance"):
                APPIUM.AppiumAdapter.validate_ios_artifact_receipt(target, hash_files=True)

    @unittest.skipIf(APPIUM.sys.platform == "darwin", "Fedora-only preinstalled strategy")
    def test_preinstalled_receipt_cannot_claim_signed_ipa_byte_binding(self) -> None:
        target = ios_target()
        target["artifactMode"] = "personal-team-preinstalled"
        target["appId"] = "org.overte.interface.e2e"
        target["capabilities"].update({
            "appium:bundleId": "org.overte.interface.e2e",
            "appium:updatedWDABundleId": "org.overte.WebDriverAgentRunner",
        })
        with tempfile.TemporaryDirectory(prefix="overte-preinstalled-receipt-") as name:
            private = Path(name)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            receipt = {
                "schemaVersion": 1,
                "contract": "overte-ios-personal-team-preinstalled-receipt-v1",
                "sourceRevision": "d" * 40,
                "createdAt": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                "notAfter": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
                "provenance": {
                    "mode": "personal-team-preinstalled",
                    "derivationBinding": "none-device-observed",
                    "cryptographicByteBinding": False,
                    "installationProxyValidated": True,
                    "bundleIdentifierMode": "fixed",
                    "attestationSha256": "e" * 64,
                    "unsignedKitContract": "overte-ios-personal-team-e2e-kit-v3",
                    "unsignedKitManifestSha256": "f" * 64,
                    "attestationContract":
                        "overte-ios-personal-team-preinstalled-attestation-v2",
                    "signingObservation": None,
                },
                "overte": {"bundleId": "org.overte.interface.e2e", "installed": True},
                "wda": {
                    "bundleId": "org.overte.WebDriverAgentRunner.xctrunner",
                    "updatedBundleId": "org.overte.WebDriverAgentRunner",
                    "bundleIdSuffix": ".xctrunner",
                    "installed": True,
                },
                "toolchain": {
                    "xcuitestDriver": "12.8.0", "remoteXpc": "5.15.3",
                    "webdriverAgent": "16.8.0",
                },
            }
            receipt_path = private / "personal-team-preinstalled-receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            receipt_path.chmod(0o600)
            target["artifactReceipt"] = str(receipt_path)
            APPIUM.AppiumAdapter.validate_ios_artifact_receipt(target, hash_files=True)
            APPIUM.AppiumAdapter.validate_ios_host_strategy(target)
            self.assertNotIn("appium:app", target["capabilities"])
            self.assertNotIn("appium:prebuiltWDAPath", target["capabilities"])

            receipt["provenance"]["bundleIdentifierMode"] = "sideloadly-remapped"
            receipt["overte"]["bundleId"] = "com.sideloadly.slot.overte"
            receipt["wda"] = {
                "bundleId": "com.sideloadly.slot.wda",
                "updatedBundleId": "com.sideloadly.slot.wda",
                "bundleIdSuffix": "",
                "installed": True,
            }
            target["appId"] = receipt["overte"]["bundleId"]
            target["capabilities"].update({
                "appium:bundleId": receipt["overte"]["bundleId"],
                "appium:updatedWDABundleId": receipt["wda"]["updatedBundleId"],
                "appium:updatedWDABundleIdSuffix": "",
            })
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            APPIUM.AppiumAdapter.validate_ios_artifact_receipt(target, hash_files=True)
            self.assertEqual("com.sideloadly.slot.wda", target["_receiptWdaBundleId"])

            target["capabilities"]["appium:prebuiltWDAPath"] = "/private/claimed.ipa"
            with self.assertRaisesRegex(RuntimeError, "must not claim signed IPA paths"):
                APPIUM.AppiumAdapter.validate_ios_host_strategy(target)

    def test_failed_post_session_attestation_deletes_session_state(self) -> None:
        adapter, client, _state, target = self.adapter_and_session()
        del adapter.ensure_session
        adapter.targets = {"private-ipad": target}
        adapter.read_session = lambda _selector: None
        adapter.validate_ios_artifact_receipt = lambda _target, hash_files=False: None
        ordering = []
        target["_artifactMode"] = "signed-ipa"
        adapter.install_receipt_bound_ios_apps = mock.Mock(
            side_effect=lambda _target: ordering.append("install"))
        adapter.pre_session_device_attestation = mock.Mock(
            side_effect=lambda _target: ordering.append("preflight"))
        with tempfile.TemporaryDirectory(prefix="overte-appium-state-") as name:
            state_path = Path(name) / "session.json"
            adapter.state_path = lambda _selector: state_path
            adapter.save_session = lambda _selector, value: state_path.write_text(
                json.dumps(value), encoding="utf-8")
            def appium_call(method, path, payload=None):
                ordering.append(path)
                return {"sessionId": "new-session"} if method == "POST" else None

            client.call = mock.Mock(side_effect=appium_call)
            adapter.attest_physical_target = mock.Mock(
                side_effect=RuntimeError("installed app contract failed"))
            with mock.patch.object(APPIUM, "WebDriver", return_value=client):
                with self.assertRaisesRegex(RuntimeError, "installed app contract failed"):
                    adapter.ensure_session("private-ipad")
            self.assertFalse(state_path.exists())
            adapter.install_receipt_bound_ios_apps.assert_called_once_with(target)
            adapter.pre_session_device_attestation.assert_called_once_with(target)
            self.assertEqual(
                ["install", "preflight", "/session", "/session/new-session"], ordering)
            self.assertEqual(mock.call("DELETE", "/session/new-session"),
                             client.call.call_args_list[-1])

    def test_cleanup_failure_is_infrastructure_error_and_retains_retry_state(self) -> None:
        adapter, client, state, _target = self.adapter_and_session()
        with tempfile.TemporaryDirectory(prefix="overte-appium-cleanup-") as name:
            state_path = Path(name) / "session.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            adapter.state_path = lambda _selector: state_path
            adapter.read_session = lambda _selector: state
            client.execute = mock.Mock(side_effect=RuntimeError("private-device-id"))
            client.call = mock.Mock(side_effect=RuntimeError("private-device-id"))
            with mock.patch.object(APPIUM, "WebDriver", return_value=client):
                with self.assertRaisesRegex(RuntimeError, "cleanup did not complete") as raised:
                    adapter.cleanup("private-ipad")
            self.assertNotIn("private-device-id", str(raised.exception))
            self.assertTrue(state_path.is_file())


if __name__ == "__main__":
    unittest.main()
