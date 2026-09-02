#!/usr/bin/env python3
"""Device-free shared Appium transport for Android and iOS targets.

Platform branches provide physical-device checks and product-specific control
channels. This adapter exposes only the common W3C surface and fails
closed for physical targets until those integrations land.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import math
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import xml.etree.ElementTree as ElementTree
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEVICE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = DEVICE_ROOT.parents[1]
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))

from adapters.common import emit, fail, parse_operation_arguments, state_directory  # noqa: E402
from contracts import (TABLET_CONTRACT_VERSION, load_tablet_ui_contract,  # noqa: E402
                       validate_operation_arguments, validate_tablet_ui_snapshot)


PLATFORMS = ("android", "ios")
TARGET_FIELDS = {
    "appId", "capabilities", "controls", "displayName", "enabled", "physical",
    "platform", "selector", "serverUrl",
}
BASE_CAPABILITIES = {
    "app.foreground", "app.install", "app.launch", "artifact.screenshot",
    "input.look", "input.move", "tablet.close", "tablet.open",
}
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_PAGE_SOURCE_BYTES = 2 * 1024 * 1024
TRANSITION_ATTEMPTS = 20
TRANSITION_RETRY_SECONDS = 0.1
TRANSITION_ERRORS = {
    "iOS semantic source must expose exactly one visible screen",
    "iOS semantic source contains duplicate visible controls",
    "iOS semantic ready marker does not match the visible screen",
}


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    return parser.parse_args()


def private_config_path(value: str) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        fail("Appium target configuration must be an absolute private path")
    absolute = raw
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.is_symlink():
            fail("Appium target configuration path must not contain symbolic links")
    try:
        metadata = absolute.lstat()
    except OSError:
        fail("Appium target configuration is unavailable")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        fail("Appium target configuration must be an ordinary private file")
    resolved = absolute.resolve(strict=True)
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        fail("Appium target configuration must be stored outside the repository")
    if (os.name != "nt"
            and (metadata.st_uid != os.geteuid()
                 or stat.S_IMODE(metadata.st_mode) != 0o600)):
        fail("Appium target configuration must be current-user-owned with mode 0600")
    return resolved


def require_point(value: object, label: str) -> list[float]:
    if (not isinstance(value, list) or len(value) != 2
            or any(not isinstance(item, (int, float)) or isinstance(item, bool)
                   or not math.isfinite(float(item))
                   or not 0.0 <= float(item) < 1.0 for item in value)):
        fail(f"{label} must contain two finite fractions from 0 inclusive through 1 exclusive")
    return [float(value[0]), float(value[1])]


def bounded_seconds(value: object, label: str) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value)) or not 0.05 <= float(value) <= 10.0):
        fail(f"{label} must be from 0.05 through 10.0 seconds")
    return float(value)


class WebDriver:
    """Small standard-library Appium W3C client with bounded responses."""

    def __init__(self, server_url: str) -> None:
        parsed = urlsplit(server_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            fail("Appium serverUrl must be a credential-free HTTP(S) URL")
        loopback = parsed.hostname == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            pass
        if parsed.scheme == "http" and not loopback:
            fail("unencrypted Appium transport is restricted to loopback")
        self.server_url = server_url.rstrip("/")

    def call(self, method: str, path: str, body: object | None = None) -> object:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.server_url + path, data=data, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError):
            fail("Appium request failed")
        if len(raw) > MAX_RESPONSE_BYTES:
            fail("Appium response exceeds the safety limit")
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            fail("Appium returned malformed JSON")
        if not isinstance(payload, dict) or "value" not in payload:
            fail("Appium returned an invalid W3C response")
        value = payload["value"]
        if isinstance(value, dict) and value.get("error"):
            fail("Appium operation failed")
        return value

    def execute(self, session: str, script: str, arguments: dict) -> object:
        return self.call("POST", f"/session/{session}/execute/sync",
                         {"script": script, "args": [arguments]})


class AppiumAdapter:
    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.adapter_id = f"appium-{platform}"
        self.targets = self.load_targets()

    def load_targets(self) -> dict[str, dict]:
        config_value = os.environ.get("OVERTE_APPIUM_TARGETS")
        if not config_value:
            fail("OVERTE_APPIUM_TARGETS must name a private target configuration")
        path = private_config_path(config_value)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("unsupported Appium target configuration schema")
        entries = payload.get("targets")
        if payload.get("schemaVersion") != 1 or not isinstance(entries, list):
            fail("unsupported Appium target configuration schema")
        targets: dict[str, dict] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                fail("Appium target configuration contains a non-object target")
            # A stale peer-platform entry cannot block this manifest.
            if entry.get("platform") != self.platform:
                continue
            selector = entry.get("selector")
            if not isinstance(selector, str) or not selector or selector in targets:
                fail("Appium target selectors must be unique non-empty strings")
            if set(entry) - TARGET_FIELDS:
                fail("Appium target contains unsupported fields")
            if not all(isinstance(entry.get(field), str) and entry[field]
                       for field in ("displayName", "serverUrl", "appId")):
                fail("Appium target requires displayName, serverUrl and appId")
            if (not isinstance(entry.get("physical"), bool)
                    or "enabled" not in entry or not isinstance(entry["enabled"], bool)):
                fail("Appium target physical and enabled flags must be boolean")
            capabilities = entry.get("capabilities")
            if not isinstance(capabilities, dict):
                fail("Appium target requires a capabilities object")
            expected = ("Android", "UiAutomator2") if self.platform == "android" else ("iOS", "XCUITest")
            if (capabilities.get("platformName"), capabilities.get("appium:automationName")) != expected:
                fail("Appium target capabilities do not match its manifest")
            controls = entry.get("controls", {})
            if not isinstance(controls, dict):
                fail("Appium target controls must be an object")
            self.validate_controls(controls)
            targets[selector] = entry
        return targets

    @staticmethod
    def validate_controls(controls: dict) -> None:
        if set(controls) - {"look", "move", "tablet"}:
            fail("Appium target contains unsupported shared controls")
        if "look" in controls:
            look = controls["look"]
            if (not isinstance(look, dict)
                    or not {"durationSeconds", "end", "start"} <= set(look)
                    or set(look) - {"durationSeconds", "end", "mode", "start"}):
                fail("Appium look control is invalid")
            if look.get("mode", "swipe") not in {"swipe", "hold"}:
                fail("Appium look control mode must be swipe or hold")
            require_point(look["start"], "look.start")
            require_point(look["end"], "look.end")
            bounded_seconds(look["durationSeconds"], "look.durationSeconds")
        if "move" in controls:
            move = controls["move"]
            directions = {"backward", "forward", "left", "right"}
            if not isinstance(move, dict) or not move or set(move) - directions:
                fail("Appium move controls must define a non-empty shared direction subset")
            for direction, gesture in move.items():
                if (not isinstance(gesture, dict)
                        or not {"durationSeconds", "end", "start"} <= set(gesture)
                        or set(gesture) - {"durationSeconds", "end", "mode", "start"}):
                    fail(f"Appium move control {direction} is invalid")
                if gesture.get("mode", "swipe") not in {"swipe", "hold"}:
                    fail(f"Appium move control {direction} mode must be swipe or hold")
                require_point(gesture["start"], f"move.{direction}.start")
                require_point(gesture["end"], f"move.{direction}.end")
                bounded_seconds(gesture["durationSeconds"],
                                f"move.{direction}.durationSeconds")
        if "tablet" in controls:
            tablet = controls["tablet"]
            allowed = {"closeAccessibilityId", "closePoint", "openAccessibilityId",
                       "openPoint", "semanticUi"}
            if not isinstance(tablet, dict) or set(tablet) - allowed:
                fail("Appium tablet control is invalid")
            for key in ("openPoint", "closePoint"):
                if key in tablet:
                    require_point(tablet[key], f"tablet.{key}")
            for key in ("openAccessibilityId", "closeAccessibilityId"):
                if key in tablet and (not isinstance(tablet[key], str) or not tablet[key]):
                    fail(f"tablet.{key} must be a non-empty accessibility ID")
            semantic = tablet.get("semanticUi")
            if semantic is not None and semantic != {"contractVersion": TABLET_CONTRACT_VERSION}:
                fail("tablet.semanticUi must opt into the current contract exactly")

    def target(self, selector: str) -> dict:
        target = self.targets.get(selector)
        if target is None:
            fail("unknown Appium target selector")
        return target

    def capabilities(self, target: dict) -> list[str]:
        result = set(BASE_CAPABILITIES)
        controls = target.get("controls", {})
        for operation, key in (("input.look", "look"), ("input.move", "move")):
            if key not in controls:
                result.discard(operation)
        tablet = controls.get("tablet", {})
        for action in ("open", "close"):
            if not (tablet.get(action + "Point") or tablet.get(action + "AccessibilityId")):
                result.discard("tablet." + action)
        if tablet.get("semanticUi"):
            result.update({"tablet.activate", "tablet.snapshot"})
        return sorted(result)

    def discover(self) -> list[dict]:
        return [{"capabilities": self.capabilities(target),
                 "displayName": target["displayName"], "physical": target["physical"],
                 "platform": self.platform, "selector": selector}
                for selector, target in sorted(self.targets.items()) if target["enabled"]]

    def describe(self, selector: str) -> dict:
        return {"capabilities": self.capabilities(self.target(selector))}

    def state_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "session.json"

    def read_session(self, selector: str) -> dict | None:
        path = self.state_path(selector)
        if path.is_symlink():
            fail("Appium session state must not be a symbolic link")
        if not path.exists():
            return None
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or os.name != "nt" and (metadata.st_uid != os.geteuid()
                                         or metadata.st_mode & 0o077)):
            fail("Appium session state is not a private ordinary file")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("Appium session state is unreadable")
        if (not isinstance(value, dict) or set(value) != {"sessionId"}
                or not isinstance(value["sessionId"], str) or not value["sessionId"]):
            fail("Appium session state is invalid")
        return value

    def save_session(self, selector: str, session: str) -> None:
        path = self.state_path(selector)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix="session.")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump({"sessionId": session}, output, separators=(",", ":"))
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    @staticmethod
    def artifact_path(filename: str) -> Path:
        root = os.environ.get("OVERTE_DEVICE_ARTIFACT_DIR")
        if not root:
            fail("artifact capture requires OVERTE_DEVICE_ARTIFACT_DIR")
        directory = Path(root).resolve()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = directory / filename
        if destination.parent != directory or destination.is_symlink():
            fail("artifact destination is unsafe")
        destination.unlink(missing_ok=True)
        return destination

    def ensure_session(self, selector: str) -> tuple[dict, WebDriver, str]:
        target = self.target(selector)
        if not target["enabled"]:
            fail("Appium target is disabled")
        if target["physical"]:
            fail("physical Appium targets require their platform integration")
        client = WebDriver(target["serverUrl"])
        state = self.read_session(selector)
        if state:
            return target, client, state["sessionId"]
        value = client.call("POST", "/session", {
            "capabilities": {"alwaysMatch": target["capabilities"], "firstMatch": [{}]},
        })
        session = value.get("sessionId") if isinstance(value, dict) else None
        if not isinstance(session, str) or not session:
            fail("Appium did not return a session ID")
        self.save_session(selector, session)
        return target, client, session

    @staticmethod
    def window_rect(client: WebDriver, session: str) -> tuple[float, float, float, float]:
        value = client.call("GET", f"/session/{session}/window/rect")
        fields = ("x", "y", "width", "height")
        if (not isinstance(value, dict)
                or not all(isinstance(value.get(field), (int, float))
                           and not isinstance(value[field], bool)
                           and math.isfinite(float(value[field])) for field in fields)
                or value["width"] <= 0 or value["height"] <= 0):
            fail("Appium returned an invalid window size")
        return tuple(float(value[field]) for field in fields)

    def gesture(self, client: WebDriver, session: str, gesture: dict,
                duration: float | None = None) -> None:
        origin_x, origin_y, width, height = self.window_rect(client, session)
        start = require_point(gesture["start"], "gesture.start")
        end = require_point(gesture["end"], "gesture.end")
        seconds = bounded_seconds(
            duration if duration is not None else gesture["durationSeconds"],
            "gesture.durationSeconds")
        milliseconds = int(seconds * 1000)
        start_x = int(origin_x) + int((width - 1) * start[0])
        start_y = int(origin_y) + int((height - 1) * start[1])
        end_x = int(origin_x) + int((width - 1) * end[0])
        end_y = int(origin_y) + int((height - 1) * end[1])
        mode = gesture.get("mode", "swipe")
        if mode not in {"swipe", "hold"}:
            fail("Appium gesture mode must be swipe or hold")
        pointer_actions = [
            {"type": "pointerMove", "duration": 0, "origin": "viewport",
             "x": start_x, "y": start_y},
            {"type": "pointerDown", "button": 0},
        ]
        if mode == "hold":
            pointer_actions.extend([
                {"type": "pointerMove", "duration": 150, "origin": "viewport",
                 "x": end_x, "y": end_y},
                {"type": "pause", "duration": milliseconds},
            ])
        else:
            pointer_actions.append(
                {"type": "pointerMove", "duration": milliseconds, "origin": "viewport",
                 "x": end_x, "y": end_y})
        pointer_actions.append({"type": "pointerUp", "button": 0})
        actions = [{"type": "pointer", "id": "overte-touch",
                    "parameters": {"pointerType": "touch"}, "actions": pointer_actions}]
        client.call("POST", f"/session/{session}/actions", {"actions": actions})

    @staticmethod
    def click_element(client: WebDriver, session: str, using: str, identifier: str) -> None:
        value = client.call("POST", f"/session/{session}/element",
                            {"using": using, "value": identifier})
        element = value.get("element-6066-11e4-a52e-4f735466cecf") if isinstance(value, dict) else None
        if not isinstance(element, str) or not element:
            fail("Appium did not return a matching accessibility element")
        client.call("POST", f"/session/{session}/element/{element}/click", {})

    def parse_semantic_source(self, source: object) -> tuple[dict, dict[str, tuple[str, str]]]:
        if not isinstance(source, str) or len(source.encode()) > MAX_PAGE_SOURCE_BYTES:
            fail("Appium page source is invalid or too large")
        if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
            fail("Appium page source contains forbidden declarations")
        try:
            root = ElementTree.fromstring(source)
        except ElementTree.ParseError:
            fail("Appium page source is malformed XML")
        contract = load_tablet_ui_contract()
        known_controls, known_screens = set(contract["controlIds"]), set(contract["screenIds"])
        screens: list[str] = []
        controls: list[str] = []
        actionable: dict[str, tuple[str, str]] = {}
        ready_screens: set[str] = set()
        ready = False
        for element in root.iter():
            values = {element.attrib.get(key, "") for key in ("resource-id", "content-desc", "name")}
            direct = set(values)
            direct.update(value.rsplit("/", 1)[-1] for value in values)
            screen_markers = {
                value.removeprefix("OverteTabletScreen.") for value in values
                if value.startswith("OverteTabletScreen.")
            }
            control_markers = {
                value.removeprefix("OverteTabletControl.") for value in values
                if value.startswith("OverteTabletControl.")
            }
            clickable = element.attrib.get("clickable", "false").lower() == "true"
            enabled = element.attrib.get("enabled", "true").lower() == "true"
            visible = element.attrib.get("visible", element.attrib.get("displayed", "true")).lower() == "true"
            if self.platform == "android":
                found_screens = {item for item in direct & known_screens
                                 if item not in known_controls or not clickable}
                if visible:
                    screens.extend(found_screens)
                matched = {item for item in direct & known_controls
                           if item not in known_screens or clickable}
                if visible:
                    controls.extend(matched)
                ready = ready or bool(found_screens) and visible and enabled
                if visible and enabled and clickable:
                    for control in matched:
                        for attribute, using in (("resource-id", "id"),
                                                 ("content-desc", "accessibility id")):
                            raw = element.attrib.get(attribute)
                            if raw and (raw == control or raw.endswith("/" + control)):
                                actionable[control] = (using, raw)
            else:
                unknown_screens = screen_markers - known_screens
                unknown_controls = control_markers - known_controls
                ready_markers = {
                    value.removeprefix("OverteTabletReady.") for value in values
                    if value.startswith("OverteTabletReady.")
                }
                unknown_ready = ready_markers - known_screens
                if unknown_screens:
                    fail("iOS semantic source contains an unknown screen marker")
                if unknown_controls:
                    fail("iOS semantic source contains an unknown control marker")
                if unknown_ready:
                    fail("iOS semantic source contains an unknown ready marker")
                if visible:
                    screens.extend(screen_markers & known_screens)
                matched = control_markers & known_controls
                if visible:
                    controls.extend(matched)
                    ready_screens.update(ready_markers & known_screens)
                if visible and enabled:
                    actionable.update({control: ("accessibility id",
                                                  "OverteTabletControl." + control)
                                       for control in matched})
        if len(screens) != 1:
            message = ("iOS semantic source must expose exactly one visible screen"
                       if self.platform == "ios"
                       else "Android semantic source must expose exactly one visible screen")
            fail(message)
        if len(controls) != len(set(controls)):
            message = ("iOS semantic source contains duplicate visible controls"
                       if self.platform == "ios"
                       else "Android semantic source contains duplicate visible controls")
            fail(message)
        if self.platform == "ios":
            if ready_screens - {screens[0]}:
                fail("iOS semantic ready marker does not match the visible screen")
            ready = screens[0] in ready_screens
        snapshot = validate_tablet_ui_snapshot({
            "contractVersion": TABLET_CONTRACT_VERSION, "schemaVersion": 1,
            "screenId": screens[0], "ready": ready,
            "visibleControlIds": sorted(set(controls)),
        }, contract)
        return snapshot, actionable

    def semantic_snapshot(self, client: WebDriver,
                          session: str) -> tuple[dict, dict[str, tuple[str, str]]]:
        attempts = TRANSITION_ATTEMPTS if self.platform == "ios" else 1
        for attempt in range(attempts):
            source = client.call("GET", f"/session/{session}/source")
            try:
                return self.parse_semantic_source(source)
            except RuntimeError as error:
                if str(error) not in TRANSITION_ERRORS or attempt == attempts - 1:
                    raise
                time.sleep(TRANSITION_RETRY_SECONDS)
        raise AssertionError("unreachable semantic transition loop")

    def invoke(self, selector: str, operation: str, values: dict) -> dict:
        try:
            arguments = validate_operation_arguments(operation, values)
        except ValueError as error:
            fail(str(error))
        target = self.target(selector)
        if operation not in self.capabilities(target):
            fail("operation is not advertised by this Appium target")
        if (operation == "input.move"
                and arguments["direction"] not in target["controls"]["move"]):
            fail("requested movement direction is not configured")
        target, client, session = self.ensure_session(selector)
        if operation == "app.install":
            source = Path(arguments["path"])
            if not source.is_file() or source.is_symlink():
                fail("application artifact must be a regular file")
            client.execute(session, "mobile: installApp", {"appPath": str(source)})
            return {"installed": True}
        if operation == "app.launch":
            client.execute(session, "mobile: activateApp", {"appId": target["appId"]})
            return {"launched": True}
        if operation == "app.foreground":
            state = client.execute(session, "mobile: queryAppState", {"appId": target["appId"]})
            return {"foreground": state == 4}
        if operation == "artifact.screenshot":
            encoded = client.call("GET", f"/session/{session}/screenshot")
            if not isinstance(encoded, str):
                fail("Appium screenshot result is invalid")
            try:
                content = base64.b64decode(encoded, validate=True)
            except ValueError:
                fail("Appium screenshot result is not base64")
            if not content:
                fail("Appium screenshot result is empty")
            destination = self.artifact_path("screenshot.png")
            destination.write_bytes(content)
            destination.chmod(0o600)
            return {"artifact": destination.name}
        controls = target["controls"]
        if operation == "input.look":
            gesture = dict(controls["look"])
            start = require_point(gesture["start"], "look.start")
            gesture["end"] = [min(.999999, max(0.0, start[0] - float(arguments["horizontal"]) * .3)),
                              min(.999999, max(0.0, start[1] - float(arguments["vertical"]) * .3))]
            self.gesture(client, session, gesture)
            return {"performed": True}
        if operation == "input.move":
            self.gesture(client, session, controls["move"][arguments["direction"]],
                         float(arguments["durationSeconds"]))
            return {"performed": True}
        if operation in {"tablet.open", "tablet.close"}:
            tablet = controls["tablet"]
            action = "open" if operation.endswith("open") else "close"
            identifier = tablet.get(action + "AccessibilityId")
            if identifier:
                self.click_element(client, session, "accessibility id", identifier)
            else:
                point = tablet[action + "Point"]
                self.gesture(client, session, {"start": point, "end": point,
                                               "durationSeconds": .05})
            return {"performed": True}
        if operation == "tablet.snapshot":
            return self.semantic_snapshot(client, session)[0]
        if operation == "tablet.activate":
            _snapshot, elements = self.semantic_snapshot(client, session)
            locator = elements.get(arguments["controlId"])
            if locator is None:
                fail("semantic tablet control is not currently actionable")
            self.click_element(client, session, locator[0], locator[1])
            return {"performed": True}
        fail("unsupported shared Appium operation")

    def cleanup(self, selector: str) -> dict:
        target = self.target(selector)
        state = self.read_session(selector)
        if state:
            WebDriver(target["serverUrl"]).call("DELETE", f"/session/{state['sessionId']}")
            self.state_path(selector).unlink(missing_ok=True)
        return {"cleaned": True}


def main() -> int:
    args = cli()
    adapter = AppiumAdapter(args.platform)
    if args.action == "discover":
        emit(adapter.discover())
    elif not args.target:
        fail(f"{args.action} requires --target")
    elif args.action == "describe":
        emit(adapter.describe(args.target))
    elif args.action == "cleanup":
        emit(adapter.cleanup(args.target))
    elif not args.operation:
        fail("invoke requires --operation")
    else:
        emit(adapter.invoke(args.target, args.operation,
                            parse_operation_arguments(args.arguments)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
