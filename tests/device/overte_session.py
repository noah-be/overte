#!/usr/bin/env python3
"""Reusable, platform-neutral behavioral API for physical Overte sessions."""

from __future__ import annotations

import json
import math
import os
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid

from contracts import (TABLET_CONTRACT_VERSION, load_tablet_ui_contract,
                       validate_operation_arguments, validate_operation_result,
                       validate_probe_snapshot)
from module_support import (InfrastructureError, assert_foreground, assert_process,
                            fail, operation, process_identity, wait_for_process,
                            wait_for_process_stopped, write_json)


class OverteSession:
    def __init__(self) -> None:
        self.poll_seconds = self._float_environment("OVERTE_E2E_POLL_SECONDS", 0.5, 0.05, 5.0)
        self.timeout_seconds = self._float_environment("OVERTE_E2E_TIMEOUT_SECONDS", 45.0, 1.0, 600.0)
        self.pico_openxr = os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1"
        self._last_sample_sequence: int | None = None

    FIXTURE_MARKERS = (
        "OVERTE_E2E_COLLISION_WALL",
        "OVERTE_E2E_EAST",
        "OVERTE_E2E_FLOOR",
        "OVERTE_E2E_NORTH",
        "OVERTE_E2E_ORIGIN",
    )
    LOOK_INPUTS = {
        "down": (0.0, -0.25, "x", -1.0),
        "left": (-0.25, 0.0, "y", -1.0),
        "right": (0.25, 0.0, "y", 1.0),
        "up": (0.0, 0.25, "x", 1.0),
    }
    INTERACTION_TARGET = "OVERTE_E2E_INTERACTABLE"

    @staticmethod
    def _float_environment(name: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(os.environ.get(name, str(default)))
        except ValueError:
            fail(f"{name} must be numeric")
        if not minimum <= value <= maximum:
            fail(f"{name} must be from {minimum} through {maximum}")
        return value

    def _invoke(self, name: str, arguments: dict | None = None) -> dict:
        try:
            validated = validate_operation_arguments(name, arguments or {})
            return validate_operation_result(name, operation(name, validated))
        except ValueError as error:
            raise InfrastructureError(str(error)) from error

    def snapshot(self, artifact: str | None = None) -> dict:
        arguments = ({} if self._last_sample_sequence is None else
                     {"afterSampleSequence": self._last_sample_sequence})
        try:
            value = validate_probe_snapshot(operation("probe.snapshot", arguments))
        except ValueError as error:
            raise InfrastructureError(str(error)) from error
        sequence = value["sampleSequence"]
        if (self._last_sample_sequence is not None
                and sequence <= self._last_sample_sequence):
            raise InfrastructureError("probe snapshot sampleSequence did not advance")
        self._last_sample_sequence = sequence
        if artifact:
            write_json(artifact, value)
        return value

    def wait_until(self, description: str, predicate: Callable[[dict], bool],
                   timeout_seconds: float | None = None) -> dict:
        deadline = time.monotonic() + (timeout_seconds or self.timeout_seconds)
        last = None
        while time.monotonic() < deadline:
            last = self.snapshot()
            if predicate(last):
                return last
            time.sleep(self.poll_seconds)
        if last is not None:
            write_json("last-probe.json", last)
        fail(f"timed out waiting for {description}")

    def load_scene(self, url: str) -> dict:
        result = self._invoke("scene.load", {"url": url})
        expected = url.split("#", 1)[0]
        marker_verification = result.get("verification") == "fixture-markers"
        command_id = result.get("commandId")
        if command_id is not None and (not isinstance(command_id, str) or not command_id):
            raise InfrastructureError("scene.load returned an invalid command identity")
        snapshot = self.wait_until(
            "the controlled scene to become ready",
            lambda value: self._fixture_ready(value) and
            (command_id is None or value["scene"].get("commandId") == command_id) and
            (marker_verification or
             self._same_scene(str(value["scene"].get("url", "")), expected)),
        )
        write_json("scene-ready.json", snapshot)
        return snapshot

    def load_controlled_scene(self) -> dict:
        return self.load_scene(os.environ.get("OVERTE_E2E_SCENE_URL", ""))

    def verify_pico_fixture(self, initial: dict) -> list[dict]:
        """Record the Pico fixture geometry and five fresh stable samples."""
        if not self.pico_openxr:
            return [initial]
        scene = initial["scene"]
        feet_position = initial["avatar"].get("feetPosition")
        if not isinstance(feet_position, dict):
            fail("Pico fixture probe did not expose the canonical feet position")
        if scene.get("fixtureMarkerCount") != len(self.FIXTURE_MARKERS):
            fail("Pico fixture did not expose all five markers")
        if (not isinstance(scene.get("floorTopY"), (int, float))
                or abs(float(scene["floorTopY"])) > 0.02):
            fail("Pico fixture floor top is not y=0")
        if scene.get("spawnValidated") is not True:
            fail("Pico fixture spawn was not validated")
        expected = {"x": 0.0, "y": 0.0, "z": 4.0}
        spawn_tolerance = self._float_environment(
            "OVERTE_E2E_SPAWN_TOLERANCE_METERS", 0.75, 0.05, 5.0)
        if self._distance(feet_position, expected) > spawn_tolerance:
            fail("Pico avatar did not stabilize near the fixture spawn")
        if (initial["avatar"].get("inAir") is not False
                or initial["avatar"].get("flying") is not False):
            fail("Pico avatar did not start grounded at the fixture spawn")

        tolerance = self._float_environment(
            "OVERTE_E2E_MAX_BASELINE_DRIFT_METERS", 0.03, 0.001, 1.0)
        samples = [initial]
        deadline = time.monotonic() + self.timeout_seconds
        while len(samples) < 5 and time.monotonic() < deadline:
            candidate = self.snapshot()
            if self._distance(samples[-1]["avatar"]["position"],
                              candidate["avatar"]["position"]) <= tolerance:
                samples.append(candidate)
            else:
                samples = [candidate]
            time.sleep(self.poll_seconds)
        if len(samples) < 5:
            fail("Pico avatar did not provide five stable fresh samples")
        write_json("fixture-stable-samples.json", samples)
        return samples

    def reload_controlled_scene(self) -> dict:
        url = os.environ.get("OVERTE_E2E_SCENE_URL", "")
        result = self._invoke("scene.reload", {"url": url})
        command_id = result.get("commandId")
        if not isinstance(command_id, str) or not command_id:
            raise InfrastructureError("scene.reload returned no command identity")
        snapshot = self.wait_until(
            "the explicitly reloaded controlled scene to become ready",
            lambda value: self._fixture_ready(value)
            and value["scene"].get("commandId") == command_id,
        )
        write_json("scene-ready.json", snapshot)
        return snapshot

    def load_asset(self, asset_id: str, url: str, entity_name: str,
                   width: int, height: int, identity: str) -> dict:
        """Request an Image entity, then require independent resource/renderer evidence."""
        if (isinstance(width, bool) or not isinstance(width, int) or width <= 0
                or isinstance(height, bool) or not isinstance(height, int) or height <= 0):
            fail("controlled asset dimensions must be positive integers")
        arguments = validate_operation_arguments("asset.load", {
            "assetId": asset_id, "url": url, "entityName": entity_name,
        })
        result = operation("asset.load", arguments)
        write_json("asset-load-command.json", result)
        assert_process(identity, "asset load request")
        assert_foreground("asset load request")

        expected_x = 1.0 if width >= height else width / height
        expected_y = height / width if width >= height else 1.0

        def ready(value: dict) -> bool:
            assert_process(identity, "asset loading")
            assert_foreground("asset loading")
            asset = value.get("asset")
            if asset is None:
                return False
            resource = asset["resource"]
            entity = asset["entity"]
            if asset["assetId"] != asset_id:
                fail("probe observed the wrong asset ID")
            if resource["url"] != url or entity["imageURL"] != url:
                fail("probe observed the wrong asset URL")
            if entity["name"] != entity_name or entity["type"] != "Image":
                fail("probe observed the wrong test entity")
            if resource["state"] == "failed":
                fail("Overte reported that the controlled asset failed")
            if resource["state"] != "finished":
                return False
            dimensions = entity["naturalDimensions"]
            tolerance = 0.0001
            return (abs(float(dimensions["x"]) - expected_x) <= tolerance
                    and abs(float(dimensions["y"]) - expected_y) <= tolerance
                    and abs(float(dimensions["z"]) - 0.01) <= tolerance)

        snapshot = self.wait_until("the controlled asset to become usable", ready)
        write_json("asset-ready.json", snapshot)
        return snapshot

    def ensure_controlled_scene(self) -> dict:
        """Reuse a ready fixture so independent modules do not restart Overte."""
        url = os.environ.get("OVERTE_E2E_SCENE_URL", "")
        if not url or "://" not in url:
            fail("OVERTE_E2E_SCENE_URL must be an absolute URL")
        try:
            snapshot = self.snapshot()
        except InfrastructureError:
            snapshot = None
        if snapshot is not None:
            expected = url.split("#", 1)[0]
            embedded = url == "overte-e2e://fixture/scene"
            scene = snapshot["scene"]
            same_scene = embedded or self._same_scene(
                str(scene.get("url", "")), expected)
            if self._fixture_ready(snapshot) and same_scene:
                write_json("scene-ready.json", snapshot)
                return snapshot
            command_id = scene.get("commandId")
            if (same_scene and isinstance(command_id, str) and command_id):
                # A prior module may observe the bounded location fallback while
                # it temporarily re-arms readiness. Waiting for that exact
                # command prevents a second scene.load from creating a reload
                # cascade across otherwise independent modules.
                snapshot = self.wait_until(
                    "the existing controlled scene command to become ready",
                    lambda value: self._fixture_ready(value)
                    and value["scene"].get("commandId") == command_id
                    and (embedded or self._same_scene(
                        str(value["scene"].get("url", "")), expected)),
                )
                write_json("scene-ready.json", snapshot)
                return snapshot
        return self.load_scene(url)

    @classmethod
    def _fixture_ready(cls, value: dict) -> bool:
        scene = value["scene"]
        return (value["application"]["running"] is True
                and scene["ready"] is True
                and scene["spawnValidated"] is True
                and tuple(scene["fixtureMarkers"]) == cls.FIXTURE_MARKERS
                and scene["fixtureMarkerCount"] == len(cls.FIXTURE_MARKERS)
                and scene["floorTopY"] is not None
                and scene["collisionWall"] is not None)

    @staticmethod
    def _parsed_domain_uuid(value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = uuid.UUID(value.strip("{}"))
        except ValueError:
            return None
        if parsed.int == 0:
            return None
        return str(parsed)

    @classmethod
    def _domain_uuid(cls, value: object, label: str) -> str:
        parsed = cls._parsed_domain_uuid(value)
        if parsed is None:
            fail(f"{label} must be a non-null UUID")
        return parsed

    @staticmethod
    def _domain_markers() -> list[str]:
        try:
            markers = json.loads(os.environ.get("OVERTE_E2E_DOMAIN_MARKERS_JSON", ""))
        except json.JSONDecodeError:
            fail("OVERTE_E2E_DOMAIN_MARKERS_JSON must be valid JSON")
        if (not isinstance(markers, list) or not markers
                or markers != sorted(set(markers))
                or not all(isinstance(item, str)
                           and item.startswith("OVERTE_E2E_DOMAIN_") for item in markers)):
            fail("OVERTE_E2E_DOMAIN_MARKERS_JSON must be a sorted unique domain marker list")
        return markers

    def enter_controlled_domain(self) -> tuple[dict, list[dict]]:
        url = os.environ.get("OVERTE_E2E_DOMAIN_URL", "")
        parsed = urlsplit(url)
        if (parsed.scheme != "hifi" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment):
            fail("OVERTE_E2E_DOMAIN_URL must be an absolute credential-free hifi URL")
        try:
            port = parsed.port
        except ValueError:
            fail("OVERTE_E2E_DOMAIN_URL contains an invalid port")
        if port is None or not 1 <= port <= 65535:
            fail("OVERTE_E2E_DOMAIN_URL must contain an explicit port")
        expected_host = os.environ.get("OVERTE_E2E_DOMAIN_HOST", "").lower()
        if not expected_host or expected_host != parsed.hostname.lower():
            fail("OVERTE_E2E_DOMAIN_HOST must match the controlled domain URL")
        expected_id = self._domain_uuid(
            os.environ.get("OVERTE_E2E_DOMAIN_ID"), "OVERTE_E2E_DOMAIN_ID")
        expected_markers = self._domain_markers()
        try:
            stable_required = int(os.environ.get("OVERTE_E2E_DOMAIN_STABLE_SAMPLES", "3"))
        except ValueError:
            fail("OVERTE_E2E_DOMAIN_STABLE_SAMPLES must be from 2 through 20")
        if not 2 <= stable_required <= 20:
            fail("OVERTE_E2E_DOMAIN_STABLE_SAMPLES must be from 2 through 20")

        identity = process_identity()
        assert_foreground("before domain navigation")
        before = self.snapshot("domain-before.json")
        before_domain = before.get("domain")
        if isinstance(before_domain, dict) and before_domain.get("connected") is True:
            if self._parsed_domain_uuid(before_domain.get("id")) == expected_id:
                fail("application was already connected to the controlled domain")

        arguments = validate_operation_arguments("navigation.enter-domain", {"url": url})
        result = operation("navigation.enter-domain", arguments)
        write_json("domain-navigation-result.json", result)
        if result.get("requested") is not True:
            fail("domain navigation operation was not accepted")

        deadline = time.monotonic() + self.timeout_seconds
        stable: list[dict] = []
        previous_entity_count = None
        last = None
        while time.monotonic() < deadline:
            last = self.snapshot()
            domain = last.get("domain")
            scene = last.get("scene", {})
            matches = False
            if isinstance(domain, dict) and domain.get("connected") is True:
                matches = (
                    self._parsed_domain_uuid(domain.get("id")) == expected_id
                    and str(domain.get("hostname", "")).lower() == expected_host
                    and domain.get("protocol") == "hifi"
                    and domain.get("serverless") is False
                    and scene.get("domainMarkers") == expected_markers
                    and scene.get("domainMarkerCount") == len(expected_markers)
                )
            entity_count = scene.get("entityCount")
            if matches and entity_count == previous_entity_count:
                stable.append(last)
            elif matches:
                stable = [last]
            else:
                stable = []
            previous_entity_count = entity_count
            if len(stable) >= stable_required:
                break
            time.sleep(self.poll_seconds)
        if len(stable) < stable_required:
            if last is not None:
                write_json("domain-last-probe.json", last)
            fail("controlled domain did not become connected with stable assignment-owned markers")
        assert_process(identity, "domain navigation")
        assert_foreground("after domain navigation")
        write_json("domain-stable-samples.json", stable)
        write_json("domain-connected.json", stable[-1])
        return stable[-1], stable

    @staticmethod
    def _same_scene(observed: str, expected: str) -> bool:
        if not observed:
            return False
        observed = observed.split("#", 1)[0]
        return observed == expected

    @staticmethod
    def _signed_angle_delta(first: dict, second: dict, axis: str) -> float:
        return (float(second[axis]) - float(first[axis]) + 180.0) % 360.0 - 180.0

    @classmethod
    def _angle_delta(cls, first: dict, second: dict) -> float:
        return math.sqrt(sum(cls._signed_angle_delta(first, second, axis) ** 2
                             for axis in ("x", "y", "z")))

    @staticmethod
    def _distance(first: dict, second: dict) -> float:
        return math.sqrt(sum((float(second[axis]) - float(first[axis])) ** 2
                             for axis in ("x", "y", "z")))

    @staticmethod
    def _planar_distance(first: dict, second: dict) -> float:
        return math.sqrt(sum((float(second[axis]) - float(first[axis])) ** 2
                             for axis in ("x", "z")))

    @staticmethod
    def _speed(snapshot: dict) -> float:
        velocity = snapshot["avatar"]["velocity"]
        return math.sqrt(sum(float(velocity[axis]) ** 2 for axis in ("x", "y", "z")))

    @staticmethod
    def _height(snapshot: dict) -> float:
        return float(snapshot["avatar"]["position"]["y"])

    def input_neutral_snapshot(self, artifact: str = "input-neutral.json") -> dict:
        previous = self.snapshot()
        stable_samples = 0
        max_speed = self._float_environment(
            "OVERTE_E2E_MAX_NEUTRAL_SPEED_MPS", 0.08, 0.001, 2.0)
        max_drift = self._float_environment(
            "OVERTE_E2E_MAX_BASELINE_DRIFT_METERS", 0.03, 0.001, 1.0)
        max_view_drift = self._float_environment(
            "OVERTE_E2E_MAX_NEUTRAL_VIEW_DEGREES", 1.0, 0.01, 20.0)

        def neutral(value: dict) -> bool:
            nonlocal previous, stable_samples
            position_drift = self._distance(
                previous["avatar"]["position"], value["avatar"]["position"])
            view_drift = self._angle_delta(
                previous["view"]["orientation"], value["view"]["orientation"])
            stable = (self._speed(value) <= max_speed
                      and position_drift <= max_drift
                      and view_drift <= max_view_drift)
            stable_samples = stable_samples + 1 if stable else 0
            previous = value
            return stable_samples >= 2

        snapshot = self.wait_until("all emulated input effects to become neutral", neutral)
        write_json(artifact, snapshot)
        return snapshot

    def stable_ground_snapshot(self, artifact: str) -> dict:
        snapshot = self.input_neutral_snapshot(artifact)
        if snapshot["avatar"]["inAir"] or snapshot["avatar"]["flying"]:
            maximum_speed = self._float_environment(
                "OVERTE_E2E_MAX_NEUTRAL_SPEED_MPS", 0.08, 0.001, 2.0)
            snapshot = self.wait_until(
                "a stable grounded avatar",
                lambda value: not value["avatar"]["inAir"]
                and not value["avatar"]["flying"]
                and self._speed(value) <= maximum_speed,
            )
            write_json(artifact, snapshot)
        return snapshot

    def assert_spawn_grounded(self) -> dict:
        maximum_speed = self._float_environment(
            "OVERTE_E2E_MAX_NEUTRAL_SPEED_MPS", 0.08, 0.001, 2.0)
        snapshot = self.wait_until(
            "a validated grounded spawn above the fixture floor",
            lambda value: self._fixture_ready(value)
            and value["scene"]["avatarAboveFloor"] is True
            and value["scene"]["spawnLocationObserved"] is True
            and not value["avatar"]["inAir"]
            and not value["avatar"]["flying"]
            and self._speed(value) <= maximum_speed
            and self._height(value) >= float(value["scene"]["floorTopY"]),
        )
        write_json("spawn-grounded.json", snapshot)
        return snapshot

    def look(self, direction: str) -> tuple[dict, dict, dict]:
        if direction not in self.LOOK_INPUTS:
            fail("look direction is unsupported")
        horizontal, vertical, axis, sign = self.LOOK_INPUTS[direction]
        before = self.input_neutral_snapshot(f"look-{direction}-before.json")
        command = self._invoke(
            "input.look", {"horizontal": horizontal, "vertical": vertical})
        write_json(f"look-{direction}-command.json", command)
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_LOOK_DEGREES", 5.0, 0.1, 90.0)
        after = self.wait_until(
            f"view orientation to turn {direction} by at least {minimum} degrees",
            lambda value: self.look_direction_delta(before, value, direction) >= minimum,
        )
        write_json(f"look-{direction}-after.json", after)
        neutral = self.input_neutral_snapshot(f"look-{direction}-neutral.json")
        return before, after, neutral

    def look_direction_delta(self, before: dict, after: dict, direction: str) -> float:
        """Return the largest directionally correct view delta observed after before."""
        if direction not in self.LOOK_INPUTS:
            fail("look direction is unsupported")
        _horizontal, _vertical, axis, sign = self.LOOK_INPUTS[direction]
        candidates = [after["view"]["orientation"]]
        candidates.extend(
            observation["orientation"]
            for observation in after["view"].get("orientationHistory", [])
            if observation["sampleSequence"] > before["sampleSequence"]
        )
        return max(sign * self._signed_angle_delta(
            before["view"]["orientation"], orientation, axis)
                   for orientation in candidates)

    def primary_interaction(self) -> tuple[dict, dict]:
        """Perform one platform-native primary action and observe its world effect."""
        before = self.snapshot("interaction-before.json")
        interaction = before.get("interaction")
        if interaction is None:
            fail("probe does not provide world interaction evidence")
        if interaction["targetAvailable"] is not True:
            fail("controlled world interaction target is unavailable")
        before_count = interaction["pressCount"]
        self._invoke("input.primary", {})

        def observed(value: dict) -> bool:
            current = value.get("interaction")
            if current is None:
                fail("probe stopped providing world interaction evidence")
            if current["targetAvailable"] is not True:
                fail("controlled world interaction target disappeared")
            if current["pressCount"] > before_count + 1:
                fail("one primary input produced duplicate world interactions")
            return (current["pressCount"] == before_count + 1
                    and current["lastEntityName"] == self.INTERACTION_TARGET)

        after = self.wait_until(
            "one primary pointer interaction on the controlled world target", observed)
        write_json("interaction-after.json", after)
        return before, after

    def scripted_entity_interaction(self) -> tuple[dict, dict]:
        """Require the entity's own downloaded script to mutate its properties."""
        ready = self.wait_until(
            "the controlled client entity script to load",
            lambda value: value.get("scriptedEntity") is not None
            and value["scriptedEntity"]["targetAvailable"] is True
            and value["scriptedEntity"]["loaded"] is True
            and value["scriptedEntity"]["state"] in {"active", "idle"},
        )
        before = dict(ready["scriptedEntity"])
        write_json("scripted-entity-before.json", before)
        self.primary_interaction()

        def activated(value: dict) -> bool:
            current = value.get("scriptedEntity")
            if current is None or current["targetAvailable"] is not True:
                fail("controlled scripted entity disappeared")
            if current["loaded"] is not True:
                fail("controlled client entity script became unloaded")
            if current["activationCount"] > before["activationCount"] + 1:
                fail("one primary input produced duplicate scripted activations")
            return (current["activationCount"] == before["activationCount"] + 1
                    and current["state"] != before["state"]
                    and current["color"] != before["color"])

        observed = self.wait_until(
            "one independent entity-script state and color mutation", activated)
        after = dict(observed["scriptedEntity"])
        write_json("scripted-entity-after.json", after)
        return before, after

    def focus_text_input(self) -> dict:
        return self._invoke("text.focus", {})

    def type_text(self, text: str, backspace_count: int, submit: bool) -> dict:
        return self._invoke("text.type", {
            "text": text,
            "backspaceCount": backspace_count,
            "submit": submit,
        })

    def dismiss_text_input(self) -> dict:
        return self._invoke("text.dismiss", {})

    def text_snapshot(self) -> dict:
        return self._invoke("text.snapshot", {})

    def wait_for_text(self, predicate: Callable[[dict], bool], description: str) -> dict:
        deadline = time.monotonic() + self.timeout_seconds
        last = None
        while time.monotonic() < deadline:
            last = self.text_snapshot()
            if predicate(last):
                return last
            time.sleep(self.poll_seconds)
        if last is not None:
            write_json("text-last.json", last)
        fail(f"timed out waiting for {description}")

    def assert_controlled_peer_roundtrip(self) -> tuple[dict, dict]:
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_PEER_MOVE_METERS", 0.25, 0.01, 10.0)

        def replicated(value: dict) -> bool:
            peer = value.get("peer")
            return (peer is not None and peer["present"] is True
                    and peer["displayName"] == "OVERTE_E2E_PEER"
                    and peer["observationCount"] >= 3
                    and peer["movementDistanceMeters"] >= minimum)

        first_sample = self.wait_until(
            f"the controlled peer and at least {minimum} meters of replicated movement",
            replicated,
        )
        first = dict(first_sample["peer"])
        write_json("peer-before-roundtrip.json", first)
        serverless = self.load_controlled_scene()
        if serverless["domain"]["connected"] or not serverless["domain"]["serverless"]:
            fail("multi-user roundtrip did not enter the controlled serverless scene")
        self.wait_until(
            "the controlled peer to leave the local avatar view",
            lambda value: value.get("peer") is not None
            and value["peer"]["present"] is False,
        )
        self.enter_controlled_domain()

        def same_peer(value: dict) -> bool:
            peer = value.get("peer")
            return (peer is not None and peer["present"] is True
                    and peer["sessionId"] == first["sessionId"]
                    and peer["movementDistanceMeters"] > first["movementDistanceMeters"])

        reconnect_sample = self.wait_until(
            "the same controlled peer and fresh replicated movement after reconnect",
            same_peer,
        )
        reconnected = dict(reconnect_sample["peer"])
        write_json("peer-after-roundtrip.json", reconnected)
        return first, reconnected

    @staticmethod
    def _domain_control(action: str) -> dict:
        url = os.environ.get("OVERTE_E2E_DOMAIN_CONTROL_URL", "")
        token = os.environ.get("OVERTE_E2E_DOMAIN_CONTROL_TOKEN", "")
        parsed = urlsplit(url)
        try:
            port = parsed.port
        except ValueError:
            port = None
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
                or port is None or parsed.path != "/v1/domain-state"
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or not token or len(token) > 256):
            fail("controlled domain recovery requires a private loopback control endpoint")
        payload = json.dumps({"schemaVersion": 1, "action": action}).encode("utf-8")
        request = Request(url, data=payload, method="POST", headers={
            "Content-Type": "application/json",
            "X-Overte-E2E-Token": token,
        })
        try:
            with urlopen(request, timeout=30) as response:
                result = json.loads(response.read(4096).decode("utf-8"))
        except (HTTPError, URLError, UnicodeError, json.JSONDecodeError, TimeoutError) as error:
            raise InfrastructureError(
                f"controlled domain {action} request failed: {type(error).__name__}") from error
        if (not isinstance(result, dict) or set(result) != {
                "generation", "schemaVersion", "state"}
                or result.get("schemaVersion") != 1
                or result.get("state") != action
                or not isinstance(result.get("generation"), int)
                or isinstance(result["generation"], bool) or result["generation"] < 1):
            raise InfrastructureError("controlled domain returned an invalid recovery response")
        return result

    def assert_network_fault_recovery(self) -> tuple[dict, dict]:
        before = self.snapshot("network-before.json")
        if before["domain"]["connected"] is not True:
            fail("network recovery did not start in a connected domain")
        expected_domain = before["domain"]["id"]
        expected_host = before["domain"]["hostname"].lower()
        expected_markers = before["scene"]["domainMarkers"]
        if not expected_markers:
            fail("network recovery started without controlled domain markers")
        identity = process_identity()
        offline = False
        try:
            self._domain_control("offline")
            offline = True
            disconnected = self.wait_until(
                "the controlled domain outage to become visible in Interface",
                lambda value: value["domain"]["connected"] is False,
            )
            write_json("network-disconnected.json", disconnected)
            assert_process(identity, "controlled domain outage")
            assert_foreground("controlled domain outage")
            self._domain_control("online")
            offline = False
        finally:
            if offline:
                try:
                    self._domain_control("online")
                except InfrastructureError:
                    pass

        stable: list[dict] = []

        def recovered(value: dict) -> bool:
            domain = value["domain"]
            scene = value["scene"]
            matches = (domain["connected"] is True
                       and self._parsed_domain_uuid(domain["id"]) ==
                       self._parsed_domain_uuid(expected_domain)
                       and domain["hostname"].lower() == expected_host
                       and scene["domainMarkers"] == expected_markers
                       and scene["domainMarkerCount"] == len(expected_markers))
            stable.append(value) if matches else stable.clear()
            return len(stable) >= 3

        reconnected = self.wait_until(
            "automatic reconnection to the exact controlled domain and content",
            recovered,
        )
        assert_process(identity, "controlled domain reconnection")
        write_json("network-reconnected.json", reconnected)
        return disconnected, reconnected

    def assert_audio_mute_roundtrip(self) -> tuple[bool, bool, bool]:
        before = self.snapshot("audio-controls-before.json")
        if before.get("audio") is None:
            fail("probe does not provide audio control evidence")
        baseline = before["audio"]["muted"]
        toggled = not baseline
        try:
            self._invoke("audio.mute", {"muted": toggled})
            changed = self.wait_until(
                f"microphone muted state to become {toggled}",
                lambda value: value.get("audio") is not None
                and value["audio"]["muted"] is toggled,
            )
            write_json("audio-controls-toggled.json", changed)
        finally:
            self._invoke("audio.mute", {"muted": baseline})
        restored_sample = self.wait_until(
            f"microphone muted state to restore to {baseline}",
            lambda value: value.get("audio") is not None
            and value["audio"]["muted"] is baseline,
        )
        write_json("audio-controls-restored.json", restored_sample)
        return baseline, toggled, restored_sample["audio"]["muted"]

    def _restart_for_setting(self) -> str:
        self._invoke("app.stop", {})
        wait_for_process_stopped()
        self._invoke("app.launch", {})
        identity = wait_for_process()
        self._last_sample_sequence = None
        assert_foreground("after settings restart")
        return identity

    def assert_setting_persistence(self) -> tuple[bool, bool]:
        before = self.snapshot("setting-before.json")
        settings = before.get("settings")
        if settings is None:
            fail("probe does not provide safe setting evidence")
        baseline = settings["audioWarnWhenMuted"]
        changed = not baseline
        restored = False
        try:
            self._invoke("setting.set", {
                "settingId": "audio.warn-when-muted", "enabled": changed})
            self.wait_until(
                f"safe setting to change to {changed}",
                lambda value: value.get("settings") is not None
                and value["settings"]["audioWarnWhenMuted"] is changed,
            )
            identity = self._restart_for_setting()
            persisted = self.wait_until(
                f"safe setting {changed} after application restart",
                lambda value: value.get("settings") is not None
                and value["settings"]["audioWarnWhenMuted"] is changed,
            )
            assert_process(identity, "settings persistence")
            write_json("setting-persisted.json", persisted)
        finally:
            process = self._invoke("app.process", {})
            if process["running"] is not True:
                self._invoke("app.launch", {})
                wait_for_process()
                self._last_sample_sequence = None
            self._invoke("setting.set", {
                "settingId": "audio.warn-when-muted", "enabled": baseline})
            self._restart_for_setting()
            restored_sample = self.wait_until(
                f"safe setting to restore persistently to {baseline}",
                lambda value: value.get("settings") is not None
                and value["settings"]["audioWarnWhenMuted"] is baseline,
            )
            write_json("setting-restored.json", restored_sample)
            restored = True
        if not restored:
            fail("safe setting restoration did not complete")
        return baseline, changed

    def assert_lifecycle_under_load(self) -> tuple[dict, dict]:
        self.set_tablet(True)
        identity = process_identity()
        before = self.snapshot("lifecycle-load-before.json")
        if before.get("render") is None:
            fail("probe does not provide renderer progress evidence")
        try:
            self._invoke("lifecycle.background", {})
            if self._invoke("app.foreground", {})["foreground"] is not False:
                fail("loaded application did not enter background")
            assert_process(identity, "loaded background transition")
            self._invoke("app.launch", {})
            assert_foreground("loaded foreground transition")
            assert_process(identity, "loaded foreground transition")
            after = self.wait_until(
                "scene, tablet, and renderer progress after foreground activation",
                lambda value: self._fixture_ready(value)
                and value["tablet"]["open"] is True
                and value.get("render") is not None
                and value["render"]["frameCount"] > before["render"]["frameCount"],
            )
            write_json("lifecycle-load-after.json", after)
            return before, after
        finally:
            self.set_tablet(False)

    def assert_render_health(self) -> tuple[dict, dict]:
        native_before = self._invoke("render.snapshot", {})
        if native_before["hardwareAccelerated"] is not True:
            fail("target presentation is not hardware accelerated")
        if native_before["surfaceVisible"] is not True:
            fail("target render surface is not visible")
        if native_before["blackFrame"] is True:
            fail("target presentation was classified as a black frame")
        probe_before = self.snapshot("render-probe-before.json")
        if probe_before.get("render") is None:
            fail("probe does not provide renderer frame evidence")
        probe_after = self.wait_until(
            "in-client renderer frames to advance",
            lambda value: value.get("render") is not None
            and value["render"]["frameCount"] > probe_before["render"]["frameCount"],
        )
        native_after = self._invoke("render.snapshot", {})
        if (native_after["backend"] != native_before["backend"]
                or native_after["hardwareAccelerated"] is not True
                or native_after["surfaceVisible"] is not True
                or native_after["blackFrame"] is True
                or native_after["frameSequence"] <= native_before["frameSequence"]):
            fail("native presentation did not remain healthy and advance")
        write_json("render-native.json", native_after)
        write_json("render-probe-after.json", probe_after)
        return native_after, probe_after

    @staticmethod
    def movement_vector(body_yaw_degrees: float, direction: str) -> tuple[float, float]:
        yaw = math.radians(float(body_yaw_degrees))
        forward = (-math.sin(yaw), -math.cos(yaw))
        right = (math.cos(yaw), -math.sin(yaw))
        axis = forward if direction in {"forward", "backward"} else right
        sign = 1.0 if direction in {"forward", "right"} else -1.0
        return axis[0] * sign, axis[1] * sign

    @classmethod
    def movement_projection(cls, before: dict, after: dict, direction: str) -> float:
        vector = cls.movement_vector(
            float(before["avatar"]["bodyYawDegrees"]), direction)
        position_before = before["avatar"]["position"]
        position_after = after["avatar"]["position"]
        displacement = (float(position_after["x"]) - float(position_before["x"]),
                        float(position_after["z"]) - float(position_before["z"]))
        return displacement[0] * vector[0] + displacement[1] * vector[1]

    @classmethod
    def direction_toward_world_negative_z(cls, body_yaw_degrees: float) -> str:
        directions = ("forward", "backward", "left", "right")
        return max(
            directions,
            key=lambda direction: -cls.movement_vector(
                body_yaw_degrees, direction)[1],
        )

    def move(self, direction: str, duration_seconds: float = 1.5) -> tuple[dict, dict, dict]:
        before = self.input_neutral_snapshot(f"move-{direction}-before.json")
        self._invoke("input.move", {
            "direction": direction,
            "durationSeconds": duration_seconds,
        })
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_MOVE_METERS", 0.2, 0.01, 20.0)
        after = self.wait_until(
            f"avatar displacement in the {direction} direction by at least {minimum} meters",
            lambda value: self.movement_projection(before, value, direction) >= minimum,
        )
        write_json(f"move-{direction}-after.json", after)
        neutral = self.input_neutral_snapshot(f"move-{direction}-neutral.json")
        if self.movement_projection(before, neutral, direction) < minimum:
            fail(f"avatar did not retain the required {direction} displacement")
        return before, after, neutral

    def jump(self) -> tuple[dict, dict, dict]:
        before = self.stable_ground_snapshot("jump-before.json")
        identity = process_identity()
        before_events = before.get("verticalEvents")
        if before_events is None:
            fail("probe does not provide vertical event history")
        before_count = before_events["jumpCount"]
        self._invoke("input.jump", {})
        minimum = self._float_environment("OVERTE_E2E_MIN_JUMP_METERS", 0.15, 0.01, 5.0)
        landing_tolerance = self._float_environment(
            "OVERTE_E2E_LANDING_TOLERANCE_METERS", 0.12, 0.01, 1.0)

        def jump_observed(value: dict) -> bool:
            events = value.get("verticalEvents")
            return (events is not None
                    and events["jumpCount"] > before_count
                    and events["lastJumpStartY"] is not None
                    and events["lastJumpPeakY"] is not None
                    and abs(events["lastJumpStartY"] - self._height(before))
                    <= landing_tolerance
                    and events["lastJumpPeakY"] - events["lastJumpStartY"] >= minimum)

        airborne = self.wait_until(
            f"a non-flying jump height gain of at least {minimum} meters",
            jump_observed,
        )
        write_json("jump-airborne.json", airborne)
        observed_count = airborne["verticalEvents"]["jumpCount"]
        landed = self.wait_until(
            f"landing within {landing_tolerance} meters of the baseline",
            lambda value: value["verticalEvents"]["jumpCompletedCount"] >= observed_count
            and value["verticalEvents"]["lastJumpLandingY"] is not None
            and abs(value["verticalEvents"]["lastJumpLandingY"]
                    - self._height(before)) <= landing_tolerance
            and value["avatar"]["inAir"] is False
            and value["avatar"]["flying"] is False
            and abs(self._height(value) - self._height(before)) <= landing_tolerance,
        )
        write_json("jump-landed.json", landed)
        assert_process(identity, "jump and landing")
        return before, airborne, landed

    def fly(self, duration_seconds: float = 2.0) -> tuple[dict, dict]:
        before = self.stable_ground_snapshot("fly-before.json")
        identity = process_identity()
        if before["avatar"]["flyingEnabled"] is not True:
            fail("avatar flying is not enabled")
        before_events = before.get("verticalEvents")
        if before_events is None:
            fail("probe does not provide vertical event history")
        before_count = before_events["flightCount"]
        self._invoke("input.fly", {"durationSeconds": duration_seconds})
        minimum = self._float_environment("OVERTE_E2E_MIN_FLY_METERS", 0.5, 0.05, 20.0)
        flying = self.wait_until(
            f"active flight with a height gain of at least {minimum} meters",
            lambda value: value["verticalEvents"]["flightCount"] > before_count
            and value["verticalEvents"]["lastFlightStartY"] is not None
            and value["verticalEvents"]["lastFlightPeakY"] is not None
            and value["verticalEvents"]["lastFlightPeakY"]
            - value["verticalEvents"]["lastFlightStartY"] >= minimum
            and value["avatar"]["flyingEnabled"] is True,
        )
        write_json("fly-active.json", flying)
        assert_process(identity, "active flight")
        return before, flying

    def set_tablet(self, opened: bool) -> dict:
        before = self.snapshot("tablet-before.json")
        if before["tablet"]["open"] is not opened:
            self._invoke("tablet.open" if opened else "tablet.close", {})
        after = self.wait_until(
            "tablet to open" if opened else "tablet to close",
            lambda value: value["tablet"]["open"] is opened,
        )
        write_json("tablet-open.json" if opened else "tablet-closed.json", after)
        return after

    def assert_tablet_input_isolation(self) -> tuple[dict, dict]:
        try:
            self.set_tablet(True)
            before = self.input_neutral_snapshot("tablet-isolation-before.json")
            maximum_drift = self._float_environment(
                "OVERTE_E2E_MAX_TABLET_WORLD_DRIFT_METERS", 0.08, 0.001, 1.0)
            maximum_speed = self._float_environment(
                "OVERTE_E2E_MAX_NEUTRAL_SPEED_MPS", 0.08, 0.001, 2.0)
            self._invoke("input.move", {"direction": "forward", "durationSeconds": 1.0})
            after = self.snapshot()
            for _ in range(2):
                if (self._planar_distance(before["avatar"]["position"],
                                          after["avatar"]["position"]) > maximum_drift
                        or self._speed(after) > maximum_speed):
                    write_json("tablet-isolation-after.json", after)
                    fail("tablet input leaked into world locomotion")
                time.sleep(self.poll_seconds)
                after = self.snapshot()
            write_json("tablet-isolation-after.json", after)
            return before, after
        finally:
            self.set_tablet(False)

    def assert_collision_wall(self) -> tuple[dict, dict]:
        self.ensure_controlled_scene()
        before = self.assert_spawn_grounded()
        wall = before["scene"]["collisionWall"]
        center = wall["center"]
        dimensions = wall["dimensions"]
        near_face_z = float(center["z"]) + float(dimensions["z"]) / 2.0
        if float(before["avatar"]["position"]["z"]) <= near_face_z:
            raise InfrastructureError("collision fixture spawn is not in front of its wall")
        direction = self.direction_toward_world_negative_z(
            float(before["avatar"]["bodyYawDegrees"]))
        self._invoke("input.move", {"direction": direction, "durationSeconds": 5.0})
        after = self.input_neutral_snapshot("collision-after.json")
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_COLLISION_APPROACH_METERS", 1.0, 0.1, 10.0)
        stopping_tolerance = self._float_environment(
            "OVERTE_E2E_COLLISION_STOP_TOLERANCE_METERS", 1.0, 0.05, 3.0)
        z = float(after["avatar"]["position"]["z"])
        if self.movement_projection(before, after, direction) < minimum:
            fail("avatar did not approach the collision wall")
        if z < near_face_z - 0.05:
            fail("avatar passed through the collision wall")
        if z > near_face_z + stopping_tolerance:
            fail("avatar stopped before reaching the collision wall")
        return before, after

    def reload_scene(self) -> tuple[dict, dict]:
        before = self.snapshot()
        scene = before["scene"]
        if before["application"]["running"] is not True:
            fail("application was not running before scene reload")
        fixture_present = (
            tuple(scene["fixtureMarkers"]) == self.FIXTURE_MARKERS
            and scene["fixtureMarkerCount"] == len(self.FIXTURE_MARKERS)
            and scene["floorTopY"] is not None
            and scene["collisionWall"] is not None
        )
        after = (self.reload_controlled_scene() if fixture_present
                 else self.load_controlled_scene())
        after = self.assert_spawn_grounded()
        if ((fixture_present
                and after["scene"]["entityCount"] != before["scene"]["entityCount"])
                or not after["scene"]["spawnValidated"]):
            fail("controlled scene reload did not restore the fixture")
        wall = after["scene"]["collisionWall"]
        near_face_z = (float(wall["center"]["z"])
                       + float(wall["dimensions"]["z"]) / 2.0)
        minimum_clearance = self._float_environment(
            "OVERTE_E2E_MIN_VERTICAL_WALL_CLEARANCE_METERS", 1.0, 0.1, 20.0)
        if float(after["avatar"]["position"]["z"]) - near_face_z < minimum_clearance:
            fail("controlled scene reload did not restore free vertical locomotion space")
        write_json("scene-reloaded.json", after)
        return before, after

    def tablet_ui_snapshot(self) -> dict:
        """Observe semantic UI state; malformed adapter evidence is infrastructure."""
        return self._invoke("tablet.snapshot", {})

    def wait_for_tablet_screen(self, screen_id: str, identity: str,
                               artifact: str) -> dict:
        vocabulary = load_tablet_ui_contract()
        if screen_id not in vocabulary["screenIds"]:
            raise InfrastructureError(f"unknown expected tablet screen: {screen_id}")
        try:
            stable_required = int(os.environ.get("OVERTE_E2E_TABLET_STABLE_SAMPLES", "2"))
        except ValueError as error:
            raise InfrastructureError(
                "OVERTE_E2E_TABLET_STABLE_SAMPLES must be from 2 through 10") from error
        if not 2 <= stable_required <= 10:
            raise InfrastructureError(
                "OVERTE_E2E_TABLET_STABLE_SAMPLES must be from 2 through 10")

        deadline = time.monotonic() + self.timeout_seconds
        stable = 0
        previous = None
        last = None
        while time.monotonic() < deadline:
            assert_process(identity, f"waiting for {screen_id}")
            last = self.tablet_ui_snapshot()
            if last["ready"] is True and last["screenId"] == screen_id:
                stable = stable + 1 if last == previous else 1
                if stable >= stable_required:
                    write_json(artifact, last)
                    return last
            else:
                stable = 0
            previous = last
            time.sleep(self.poll_seconds)
        if last is not None:
            write_json("tablet-ui-last.json", last)
        fail(f"timed out waiting for ready stable tablet screen {screen_id}")

    def activate_tablet_control(self, control_id: str, identity: str) -> dict:
        result = self._invoke("tablet.activate", {
            "contractVersion": TABLET_CONTRACT_VERSION,
            "controlId": control_id,
        })
        assert_process(identity, f"activating {control_id}")
        return result
