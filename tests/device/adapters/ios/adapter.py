#!/usr/bin/env python3
"""Extend the strict iOS Appium contract with real native/client operations.

The injected Wi-Fi driver provides bounded DVT process observation and signals.
HTTP is only the command delivery channel: client receipts and fresh probes
verify execution, and the portable modules verify the resulting behavior.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import json
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid

from adapters.appium.adapter import AppiumAdapter
from adapters.common import fail
from contracts import validate_operation_arguments
from adapters.ios import native_ui


class IOSAdapter(AppiumAdapter):
    CLIENT_OPERATIONS = frozenset({
        "asset.load", "audio.mute", "navigation.enter-domain", "setting.set",
    })
    NATIVE_OPERATIONS = frozenset({
        "app.crash", "app.stop", "app.version", "lifecycle.background",
    })

    def __init__(self):
        super().__init__("ios")

    @staticmethod
    def advertised_capabilities(target):
        values = set(AppiumAdapter.advertised_capabilities(target))
        if (target.get("platform") == "ios" and target.get("physical") is True
                and target.get("testBuild")
                and target.get("probe") == {"kind": "ios-documents"}):
            values |= IOSAdapter.CLIENT_OPERATIONS | IOSAdapter.NATIVE_OPERATIONS
        return sorted(values)

    @staticmethod
    def native_process(client, session, target):
        value = client.execute(session, "mobile: overteProcessInfo",
                               {"bundleId": target["appId"]})
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) != {"bundleId", "pid", "foreground"}
                or value["bundleId"] != target["appId"]
                or type(value["pid"]) is not int or value["pid"] <= 0
                or type(value["foreground"]) is not bool):
            fail("native iOS process observation is invalid")
        return value

    def process_state(self, selector, client, session, state, target):
        process = self.native_process(client, session, target)
        if process is None:
            return {"running": False, "identity": None}
        identity = str(process["pid"])
        if state.get("processIdentity") not in (None, identity):
            raise RuntimeError("ASSERTION: iOS process restarted unexpectedly")
        state["processIdentity"] = identity
        self.save_session(selector, state)
        return {"running": True, "identity": identity}

    def assert_ios_process_identity(self, selector, client, session, state, target):
        # One fresh DVT observation verifies bundle, executable, PID and
        # foreground state together. No process facts are cached between calls.
        process = self.native_process(client, session, target)
        if process is None or process["foreground"] is not True:
            raise RuntimeError("ASSERTION: iOS application is not foregrounded")
        identity = str(process["pid"])
        expected = state.get("processIdentity")
        if expected is not None and expected != identity:
            raise RuntimeError("ASSERTION: iOS application process restarted during the E2E sequence")
        if expected is None:
            state["processIdentity"] = identity
            self.save_session(selector, state)
        return identity

    def command(self, selector, client, session, state, target, action, **arguments):
        identity = self.assert_ios_process_identity(selector, client, session, state, target)
        command_id = "ios-" + uuid.uuid4().hex
        payload = {"schemaVersion": 1, "commandId": command_id,
                   "action": action, **arguments}
        origin = target["testBuild"]["fixtureOrigin"]
        self.controlled_http_url(origin, "iOS fixture command origin")
        request = Request(origin + "/e2e-client-command.json",
                          data=json.dumps(payload).encode(), method="POST",
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            content = response.read(4097)
            if response.status != 200 or len(content) > 4096:
                fail("owned fixture did not accept the exact client command")
        if json.loads(content) != payload:
            fail("owned fixture changed the client command")
        remote = (f"@{target['appId']}:documents/"
                  f"{target['testBuild']['resultsDirectory']}/client-command-result.json")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.assert_ios_process_identity(selector, client, session, state, target) != identity:
                fail("iOS client command crossed process identities")
            encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
            try:
                observed = json.loads(base64.b64decode(encoded, validate=True))
            except (ValueError, UnicodeError):
                time.sleep(0.05)
                continue
            if (isinstance(observed, dict) and set(observed) == {
                    "schemaVersion", "commandId", "sampleEpochMs"}
                    and type(observed["schemaVersion"]) is int and observed["schemaVersion"] == 1
                    and observed["commandId"] == command_id
                    and type(observed["sampleEpochMs"]) in (int, float)
                    and -1000 <= time.time() * 1000 - observed["sampleEpochMs"] <= 5000):
                return command_id
            time.sleep(0.1)
        fail("fresh iOS client execution receipt was not observed")

    def reset_launch_state(self, selector, state):
        for key in ("processIdentity", "iosE2ELaunchCompleted", "iosE2ESceneUrl"):
            state.pop(key, None)
        self.save_session(selector, state)

    @staticmethod
    def native_ui_enabled(target):
        value = target.get("nativeUiObservation")
        return (value == {"kind": "uikit-documents", "version": 1}
                and type(value.get("version")) is int)

    def native_ui_snapshot(self, client, session, target):
        process = self.native_process(client, session, target)
        if process is None or not process["foreground"]:
            fail("native UIKit observation requires the configured foreground process")
        remote = (f"@{target['appId']}:documents/"
                  f"{target['testBuild']['resultsDirectory']}/ios-native-ui.json")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
            try:
                document = native_ui.validate(json.loads(base64.b64decode(encoded, validate=True)), process["pid"])
            except (ValueError, UnicodeError):
                time.sleep(0.1)
                continue
            after = self.native_process(client, session, target)
            if after != process:
                raise RuntimeError("ASSERTION: native UIKit observation crossed process or foreground identities")
            return document
        fail("fresh native UIKit accessibility observation was not available")

    def ios_tablet_observation(self, selector, client, session, state, target):
        if not self.native_ui_enabled(target):
            return super().ios_tablet_observation(selector, client, session, state, target)
        self.assert_ios_process_identity(selector, client, session, state, target)
        document = self.native_ui_snapshot(client, session, target)
        return self.parse_ios_tablet_source(native_ui.source(document))

    def click_accessibility(self, client, session, identifier):
        target = getattr(self, "_native_ui_target", None)
        if target is None or not self.native_ui_enabled(target):
            return super().click_accessibility(client, session, identifier)
        document = self.native_ui_snapshot(client, session, target)
        matches = [e for e in document["elements"] if e["identifier"] == identifier
                   and e["visible"] and e["enabled"]]
        if len(matches) != 1:
            fail("native UIKit activation requires one observed visible enabled control")
        frame = matches[0]["frame"]
        x, y = round(frame["x"] + frame["width"] / 2), round(frame["y"] + frame["height"] / 2)
        body = {"actions": [{"type": "pointer", "id": "overte-native-widget", "parameters": {"pointerType": "touch"},
            "actions": [
                {"type": "pointerMove", "duration": 0, "origin": "viewport", "x": x, "y": y},
                {"type": "pointerDown", "button": 0}, {"type": "pause", "duration": 80},
                {"type": "pointerUp", "button": 0}]}]}
        try:
            client.call("POST", f"/session/{session}/actions", body)
        finally:
            client.call("DELETE", f"/session/{session}/actions")

    def invoke(self, selector, operation, values):
        if operation in {"accessibility.snapshot", "tablet.open", "tablet.close", "tablet.activate", "tablet.snapshot"}:
            target = self.target(selector)
            if self.native_ui_enabled(target):
                self._native_ui_target = target
                try:
                    if operation == "accessibility.snapshot":
                        if values != {}:
                            fail("native UIKit accessibility observation does not accept arguments")
                        client, session, state = self.ensure_session(selector)
                        self.assert_ios_process_identity(selector, client, session, state, target)
                        return {"source": native_ui.source(self.native_ui_snapshot(client, session, target)), "artifact": None}
                    return super().invoke(selector, operation, values)
                finally:
                    del self._native_ui_target
        extended = self.CLIENT_OPERATIONS | self.NATIVE_OPERATIONS | {"app.process"}
        if operation not in extended:
            return super().invoke(selector, operation, values)
        arguments = validate_operation_arguments(operation, values)
        target = self.target(selector)
        if operation not in self.advertised_capabilities(target):
            fail("iOS native operation requires a physical observed test client")
        # Reject foreign fixture assets before creating a device session.
        if operation == "asset.load":
            if self.controlled_http_url(arguments["url"], "asset URL") != self.controlled_http_url(
                    target["testBuild"]["fixtureOrigin"], "fixture origin"):
                fail("iOS asset must belong to the owned fixture")
        if operation == "navigation.enter-domain":
            parsed = urlsplit(arguments["url"])
            fixture = urlsplit(target["testBuild"]["fixtureOrigin"])
            if parsed.hostname != fixture.hostname:
                fail("iOS navigation must remain on the owned lab host")
        client, session, state = self.ensure_session(selector)
        if operation == "app.process":
            return self.process_state(selector, client, session, state, target)
        if operation == "app.stop":
            client.execute(session, "mobile: terminateApp", {"bundleId": target["appId"]})
            if self.native_process(client, session, target) is not None:
                fail("configured iOS process did not stop")
            self.reset_launch_state(selector, state)
            return {"stopped": True}
        if operation == "app.crash":
            self.assert_ios_process_identity(selector, client, session, state, target)
            client.execute(session, "mobile: overteAbortApp", {"bundleId": target["appId"]})
            if self.native_process(client, session, target) is not None:
                fail("configured iOS process did not exit after SIGABRT")
            self.reset_launch_state(selector, state)
            return {"crashed": True}
        if operation == "app.version":
            snapshot = self.probe_snapshot(selector, client, session, state, target)
            return {"schemaVersion": 1, "version": snapshot["build"]["version"]}
        if operation == "lifecycle.background":
            before = self.native_process(client, session, target)
            if before is None or not before["foreground"]:
                fail("native background requires the configured foreground process")
            client.execute(session, "mobile: pressButton", {"name": "home"})
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                after = self.native_process(client, session, target)
                if after is None or after["pid"] != before["pid"]:
                    raise RuntimeError("ASSERTION: iOS background lost the original process")
                if not after["foreground"]:
                    return {"backgrounded": True}
                time.sleep(0.1)
            fail("iOS background transition was not observed")
        if operation == "navigation.enter-domain":
            self.command(selector, client, session, state, target, "navigate", **arguments)
            return {"requested": True}
        if operation == "asset.load":
            self.command(selector, client, session, state, target, "asset-load", **arguments)
            return {"requested": True}
        if operation == "setting.set":
            self.command(selector, client, session, state, target, "set-safe-setting", **arguments)
        elif operation == "audio.mute":
            self.command(selector, client, session, state, target, "set-audio-mute", **arguments)
        else:
            fail("unsupported extended iOS operation")
        return {"performed": True}
