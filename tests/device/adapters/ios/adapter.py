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
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid

from adapters.appium.adapter import AppiumAdapter
from adapters.common import fail
from contracts import validate_operation_arguments
from adapters.ios import native_ui, native_integration, native_primary, native_upgrade
from adapters.collaboration_observation import actor_receipt, portable_observation


class IOSAdapter(AppiumAdapter):
    CLIENT_OPERATIONS = frozenset({
        "asset.load", "audio.mute", "navigation.enter-domain", "setting.set",
    })
    NATIVE_OPERATIONS = frozenset({
        "app.crash", "app.stop", "app.version", "lifecycle.background",
    })

    COLLABORATION_OPERATIONS = frozenset({"collaboration.edit", "collaboration.snapshot"})
    INTEGRATION_OPERATIONS = frozenset({"text.focus", "text.type", "text.snapshot", "text.dismiss", "render.snapshot"})

    def __init__(self):
        super().__init__("ios")

    @staticmethod
    def advertised_capabilities(target):
        values = set(AppiumAdapter.advertised_capabilities(target))
        if (target.get("platform") == "ios" and target.get("physical") is True
                and target.get("testBuild")
                and target.get("probe") == {"kind": "ios-documents"}):
            values |= IOSAdapter.CLIENT_OPERATIONS | IOSAdapter.NATIVE_OPERATIONS
            if native_integration.enabled(target):
                values |= IOSAdapter.INTEGRATION_OPERATIONS
            if native_primary.enabled(target):
                values.add("input.primary")
            if native_upgrade.configuration(target) is not None:
                values |= {"app.install", "app.upgrade"}
            if IOSAdapter.collaboration_configuration(target) is not None:
                values |= IOSAdapter.COLLABORATION_OPERATIONS
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

    def launch_ios_test_build(self, selector, client, session, state, target, scene_url=None,
                              *, reactivate=False):
        new_process = state.get("iosE2ELaunchCompleted") is not True
        launched_at = int(time.time() * 1000)
        super().launch_ios_test_build(selector, client, session, state, target, scene_url,
                                     reactivate=reactivate)
        if not new_process:
            return
        # Documents survives process restarts. Wait for this launch's first
        # actual observation instead of returning a previous process's file
        # while its replacement script is still starting. This bounded wait
        # applies only at launch; normal stale observations remain failures.
        identity = self.assert_ios_process_identity(selector, client, session, state, target)
        remote = f"@{target['appId']}:documents/{target['testBuild']['resultsDirectory']}/overte-probe.json"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.assert_ios_process_identity(selector, client, session, state, target) != identity:
                fail("first iOS observation crossed launch process identities")
            encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
            try:
                observed = json.loads(base64.b64decode(encoded, validate=True))
            except (ValueError, UnicodeError):
                time.sleep(0.1)
                continue
            epoch = observed.get("sampleEpochMs") if isinstance(observed, dict) else None
            if type(epoch) is int and epoch >= launched_at:
                self.validate_probe(observed)
                self.assert_ios_process_identity(selector, client, session, state, target)
                return
            time.sleep(0.1)
        fail("this iOS launch did not produce a fresh first probe observation")

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

    @classmethod
    def collaboration_configuration(cls, target):
        config = target.get("collaboration")
        if config is None:
            return None
        if (not isinstance(config, dict) or set(config) != {"kind", "stateUrl", "editUrl", "token", "domainId", "domainUrl"}
                or config["kind"] != "owned-domain"
                or any(not isinstance(value, str) for value in config.values())
                or not isinstance(config["token"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", config["token"])
                or not isinstance(config["domainId"], str)
                or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", config["domainId"])
                or config["domainId"] == "00000000-0000-0000-0000-000000000000"):
            fail("independent iOS collaboration configuration is invalid")
        for kind in ("state", "edit"):
            parsed = urlsplit(config[kind + "Url"])
            if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.path != "/v1/collaboration-" + kind):
                fail("independent iOS collaboration control must be on the owned loopback fixture")
        if self_origin := cls.controlled_http_url(config["stateUrl"], "actor state origin"):
            if self_origin != cls.controlled_http_url(config["editUrl"], "actor edit origin"):
                fail("independent actor state and edit must use one owned control server")
        domain = urlsplit(config["domainUrl"])
        fixture = urlsplit(target["testBuild"]["fixtureOrigin"])
        if (domain.scheme != "hifi" or domain.hostname != fixture.hostname or not domain.port
                or domain.username or domain.password):
            fail("independent collaboration domain must be on the owned lab host")
        return config

    def collaboration_request(self, target, kind, payload=None):
        config = self.collaboration_configuration(target)
        if config is None:
            fail("independent iOS collaboration is not configured")
        request = Request(config[kind + "Url"], data=None if payload is None else json.dumps(payload).encode(),
                          headers={"X-Overte-E2E-Token": config["token"], "Content-Type": "application/json"},
                          method="GET" if payload is None else "POST")
        try:
            with urlopen(request, timeout=5) as response:
                body = response.read(4097)
                if response.status != 200 or len(body) > 4096:
                    fail("independent actor response exceeded its contract")
                result = json.loads(body)
                if kind == "state":
                    actor_receipt(result)
                return result
        except HTTPError as error:
            if kind == "state" and error.code == 503:
                return None
            fail("independent actor rejected the requested operation")
        except (URLError, OSError, ValueError):
            fail("independent actor control is unavailable or malformed")

    def collaboration_snapshot(self, selector, client, session, state, target):
        config = self.collaboration_configuration(target)
        identity = self.assert_ios_process_identity(selector, client, session, state, target)
        probe = self.probe_snapshot(selector, client, session, state, target)
        if str(probe["domain"]["id"]).strip("{}").lower() != config["domainId"] or not probe["domain"]["connected"]:
            self.command(selector, client, session, state, target, "navigate", url=config["domainUrl"])
        remote = f"@{target['appId']}:documents/{target['testBuild']['resultsDirectory']}/e2e-collaboration-observation.json"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            actor = self.collaboration_request(target, "state")
            probe = self.probe_snapshot(selector, client, session, state, target)
            encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
            try:
                observed = json.loads(base64.b64decode(encoded, validate=True))
                portable = portable_observation(observed, actor, time.time() * 1000, probe) if actor else None
            except (ValueError, UnicodeError):
                portable = None
            if portable and probe["domain"]["connected"] and str(probe["domain"]["id"]).strip("{}").lower() == config["domainId"]:
                if self.assert_ios_process_identity(selector, client, session, state, target) != identity:
                    fail("collaboration crossed process identities")
                return portable
            self.assert_ios_process_identity(selector, client, session, state, target)
            time.sleep(0.1)
        fail("independent native actor and replicated client entity did not match")

    def native_text_command(self, selector, client, session, state, target, action):
        identity = self.assert_ios_process_identity(selector, client, session, state, target)
        command_id = "ios-" + uuid.uuid4().hex
        payload = {"schemaVersion": 1, "commandId": command_id,
                   "action": "text-fixture", "operation": action}
        origin = target["testBuild"]["fixtureOrigin"]
        self.controlled_http_url(origin, "native text fixture origin")
        request = Request(origin + "/e2e-client-command.json", data=json.dumps(payload).encode(),
                          method="POST", headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            body = response.read(4097)
            if response.status != 200 or len(body) > 4096 or json.loads(body) != payload:
                fail("owned fixture did not accept the exact native text command")
        remote = f"@{target['appId']}:documents/{target['testBuild']['resultsDirectory']}/ios-text-observation.json"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.assert_ios_process_identity(selector, client, session, state, target) != identity:
                fail("native text command crossed process identities")
            encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
            try:
                observed = native_integration.text(json.loads(base64.b64decode(encoded, validate=True)), int(identity), command_id)
            except (ValueError, UnicodeError):
                time.sleep(0.1)
                continue
            self.assert_ios_process_identity(selector, client, session, state, target)
            return observed
        fail("fresh actual native text execution was not observed")

    def native_render_snapshot(self, selector, client, session, state, target):
        identity = self.assert_ios_process_identity(selector, client, session, state, target)
        remote = f"@{target['appId']}:documents/{target['testBuild']['resultsDirectory']}/ios-render-observation.json"
        encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
        document = native_integration.render(json.loads(base64.b64decode(encoded, validate=True)), int(identity))
        # A native presentation counter alone cannot prove visible pixels.
        # Classify a contemporaneous physical screenshot of the world surface.
        from io import BytesIO
        from PIL import Image
        image_data = base64.b64decode(client.call("GET", f"/session/{session}/screenshot"), validate=True)
        if not image_data or len(image_data) > 24 * 1024 * 1024:
            fail("native render screenshot exceeded its byte bound")
        with Image.open(BytesIO(image_data)) as image:
            if image.width * image.height > 24 * 1024 * 1024:
                fail("native render screenshot exceeded its pixel bound")
            # Exclude edge controls and status bars; require scene pixels in
            # the central world region, rather than a lit toolbar on black.
            crop = image.crop((image.width // 4, image.height // 4,
                               image.width * 3 // 4, image.height * 3 // 4)).convert("RGB")
            crop.thumbnail((128, 128))
            pixels = list(crop.getdata())
            non_black = sum(max(pixel) > 12 for pixel in pixels)
            black = non_black < max(1, len(pixels) // 100)
        self.assert_ios_process_identity(selector, client, session, state, target)
        return {"schemaVersion": 1, "backend": document["backend"],
                "hardwareAccelerated": document["hardwareAccelerated"],
                "surfaceVisible": document["surfaceVisible"], "blackFrame": black,
                "frameSequence": document["frameSequence"]}

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
        extended = self.CLIENT_OPERATIONS | self.NATIVE_OPERATIONS | self.INTEGRATION_OPERATIONS | self.COLLABORATION_OPERATIONS | {"app.process", "input.primary", "scene.load", "scene.reload", "app.install", "app.upgrade"}
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
        upgrade = native_upgrade.configuration(target) if operation in {"app.install", "app.upgrade"} else None
        if upgrade is not None:
            if operation == "app.install" and arguments["path"] != upgrade["source"]["path"]:
                fail("native install requires the exact prepared source artifact")
            if operation == "app.upgrade" and arguments != {
                    "fromVersion":upgrade["source"]["version"],"toVersion":upgrade["candidate"]["version"]}:
                fail("native upgrade requires the exact prepared version pair")
        client, session, state = self.ensure_session(selector)
        if upgrade is not None:
            if operation == "app.upgrade":
                observed = self.probe_snapshot(selector,client,session,state,target)
                if observed["build"]["version"] != arguments["fromVersion"]:
                    fail("native upgrade did not start in the independently observed source version")
                client.execute(session,"mobile: terminateApp",{"bundleId":target["appId"]})
            if self.native_process(client,session,target) is not None:
                fail("native installation requires the configured application process to be stopped")
            role = "source" if operation == "app.install" else "candidate"
            receipt = client.execute(session,"mobile: overteInstallArtifact",{"role":role})
            if receipt != {"installed":True,"sha256":upgrade[role]["sha256"]}:
                fail("native installation service did not acknowledge the exact prepared package")
            self.reset_launch_state(selector,state)
            if operation == "app.install":
                return {"installed":True}
            self.launch_ios_test_build(selector,client,session,state,target,reactivate=True)
            actual = self.probe_snapshot(selector,client,session,state,target)
            if actual["build"]["version"] != arguments["toVersion"]:
                fail("native installed candidate did not report the requested version")
            return {"applied":True}
        if operation in {"scene.load", "scene.reload"}:
            url = arguments["url"]
            self.launch_ios_test_build(selector, client, session, state, target, url)
            # launch_ios_test_build deliberately preserves an existing process.
            # Therefore even scene.load must deliver a real scene command;
            # relaunch validation alone leaves an existing domain unchanged.
            nonce = self.request_ios_scene_reload(selector, client, session, state, target, url)
            return {"requested": True, "verification": "fixture-markers", "commandId": nonce}
        if operation == "input.primary":
            identity = self.assert_ios_process_identity(selector, client, session, state, target)
            try:
                nonce = self.command(selector, client, session, state, target, "primary-view", operation="prepare")
                remote = f"@{target['appId']}:documents/{target['testBuild']['resultsDirectory']}/ios-primary-observation.json"
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    self.assert_ios_process_identity(selector, client, session, state, target)
                    encoded = client.execute(session, "mobile: pullFile", {"remotePath": remote})
                    try:
                        point = native_primary.point(json.loads(base64.b64decode(encoded, validate=True)), nonce)
                    except (ValueError, UnicodeError):
                        time.sleep(0.1)
                        continue
                    self.tap_fractional_point(client, session, point, "independently picked world entity")
                    if self.assert_ios_process_identity(selector, client, session, state, target) != identity:
                        fail("world interaction crossed process identities")
                    return {"performed": True}
                fail("controlled world entity was not independently picked in the viewport")
            finally:
                self.command(selector, client, session, state, target, "primary-view", operation="restore")
        if operation in self.COLLABORATION_OPERATIONS:
            observed = self.collaboration_snapshot(selector, client, session, state, target)
            if operation == "collaboration.snapshot":
                return observed
            if arguments["entityName"] != observed["entityName"]:
                fail("collaboration edit requires the independently observed fixture entity")
            self.collaboration_request(target, "edit", {"schemaVersion": 1, **arguments})
            self.assert_ios_process_identity(selector, client, session, state, target)
            return {"performed": True}
        if operation in self.INTEGRATION_OPERATIONS:
            self.assert_ios_process_identity(selector, client, session, state, target)
            if operation == "render.snapshot":
                return self.native_render_snapshot(selector, client, session, state, target)
            if operation == "text.type":
                before = self.native_text_command(selector, client, session, state, target, "snapshot")
                if not before["focused"]:
                    fail("native keyboard input requires the controlled focused field")
                # XCTest sends actual native keyboard events. No assignment to
                # field values or submit counters is available in the bridge.
                client.execute(session, "mobile: overteTypeText", arguments)
                self.assert_ios_process_identity(selector, client, session, state, target)
                return {"performed": True}
            action = {"text.focus": "focus", "text.snapshot": "snapshot", "text.dismiss": "dismiss"}[operation]
            observed = self.native_text_command(selector, client, session, state, target, action)
            return observed if operation == "text.snapshot" else {"performed": True}
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
