#!/usr/bin/env python3
"""Reusable, platform-neutral behavioral API for physical Overte sessions."""

from __future__ import annotations

import json
import math
import os
import time
from typing import Callable
from urllib.parse import urlsplit
import uuid

from contracts import (validate_operation_arguments, validate_operation_result,
                       validate_probe_snapshot)
from module_support import (InfrastructureError, assert_foreground, assert_process,
                            fail, operation, process_identity, write_json)


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
        snapshot = self.wait_until(
            "the controlled scene to become ready",
            lambda value: self._fixture_ready(value) and
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
        position = initial["avatar"]["position"]
        if scene.get("fixtureMarkerCount") != len(self.FIXTURE_MARKERS):
            fail("Pico fixture did not expose all five markers")
        if (not isinstance(scene.get("floorTopY"), (int, float))
                or abs(float(scene["floorTopY"])) > 0.02):
            fail("Pico fixture floor top is not y=0")
        if scene.get("spawnValidated") is not True:
            fail("Pico fixture spawn was not validated")
        expected = {"x": 0.0, "y": float(position["y"]), "z": 4.0}
        spawn_tolerance = self._float_environment(
            "OVERTE_E2E_SPAWN_TOLERANCE_METERS", 0.75, 0.05, 5.0)
        if self._planar_distance(position, expected) > spawn_tolerance:
            fail("Pico avatar did not stabilize near the fixture spawn")

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
            if (self._fixture_ready(snapshot)
                    and (embedded or self._same_scene(str(scene.get("url", "")), expected))):
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
        arguments = {"horizontal": horizontal, "vertical": vertical}
        if self.pico_openxr:
            # Physical Pico frame/probe observations can be several seconds
            # apart. Keep the bounded override active across at least two such
            # observations; the native watchdog still neutralizes it.
            arguments["durationSeconds"] = 6.0
            result = validate_operation_result(
                "input.look", operation("input.look", arguments))
        else:
            result = self._invoke("input.look", arguments)
        write_json("look-input-result.json", result)
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_LOOK_DEGREES", 5.0, 0.1, 90.0)

        if self.pico_openxr:
            yaw = result.get("viewYawDegrees")
            pitch = result.get("viewPitchDegrees")
            if (result.get("viewApplied") is not True
                    or not isinstance(yaw, (int, float)) or isinstance(yaw, bool)
                    or not isinstance(pitch, (int, float)) or isinstance(pitch, bool)
                    or math.hypot(float(yaw), float(pitch)) < minimum):
                fail("Pico OpenXR view override lacks native consumption evidence")

        def changed_in_direction(value: dict) -> bool:
            changed = sign * self._signed_angle_delta(
                before["view"]["orientation"], value["view"]["orientation"], axis)
            if changed < minimum:
                return False
            if not self.pico_openxr:
                return True
            controller = value.get("controller", {})
            axes = controller.get("axes", {})
            openxr = controller.get("route", {}).get("openxrAxes")
            return (all(abs(float(axes.get(name, 1.0))) <= 0.05
                        for name in ("lx", "ly", "rx", "ry"))
                    and isinstance(openxr, dict)
                    and all(abs(float(openxr.get(name, 1.0))) <= 0.05
                            for name in ("lx", "ly", "rx", "ry")))

        after = self.wait_until(
            f"view orientation to turn {direction} by at least {minimum} degrees",
            changed_in_direction,
        )
        write_json(f"look-{direction}-after.json", after)
        neutral = self.input_neutral_snapshot(f"look-{direction}-neutral.json")
        return before, after, neutral

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
        if self.pico_openxr:
            input_state = before.get("input", {})
            if input_state.get("dominantHand") != "right":
                fail("Pico movement requires effective right-hand dominance")
            if input_state.get("advancedMovementControls") is not True:
                fail("Pico movement requires effective advanced movement controls")
        move_arguments = {
            "direction": direction,
            "durationSeconds": duration_seconds,
        }
        if self.pico_openxr:
            move_arguments.update({"durationSeconds": 3.0, "strength": 0.4})
            result = validate_operation_result(
                "input.move", operation("input.move", move_arguments))
        else:
            result = self._invoke("input.move", move_arguments)
        write_json("move-input-result.json", result)
        if self.pico_openxr:
            applied_y = result.get("openXrLeftThumbstickY")
            if (result.get("openXrVectorApplied") is not True
                    or not isinstance(applied_y, (int, float))
                    or isinstance(applied_y, bool) or abs(float(applied_y)) < 0.15):
                fail("Pico movement lacks native OpenXR vector consumption evidence")
            route_minimum = self._float_environment(
                "OVERTE_E2E_MIN_ROUTE_AXIS", 0.15, 0.01, 1.0)

            def complete_route(value: dict) -> bool:
                route = value.get("controller", {}).get("route", {})
                openxr = route.get("openxrAxes")
                if not isinstance(openxr, dict):
                    return False
                values = [openxr.get("ly"), route.get("standardLy"),
                          route.get("translateZAction"),
                          route.get("rawTranslateZDriveKey")]
                if (any(not isinstance(item, (int, float)) or isinstance(item, bool)
                        for item in values)
                        or any(abs(float(item)) < route_minimum for item in values)
                        or route.get("translateZDriveKeyDisabled") is not False):
                    return False
                mapped_signs = [float(item) > 0.0 for item in values[:3]]
                raw_sign = float(values[3]) > 0.0
                # The controller/action axes use the OpenXR forward convention;
                # MyAvatar's raw TranslateZ DriveKey exposes the inverse sign.
                return len(set(mapped_signs)) == 1 and raw_sign != mapped_signs[0]

            route_snapshot = self.wait_until(
                "the complete Pico movement route to become active", complete_route)
            write_json("move-route-active.json", route_snapshot)
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
        self._invoke("input.jump", {})
        minimum = self._float_environment("OVERTE_E2E_MIN_JUMP_METERS", 0.15, 0.01, 5.0)
        airborne = self.wait_until(
            f"a non-flying jump height gain of at least {minimum} meters",
            lambda value: value["avatar"]["inAir"] is True
            and value["avatar"]["flying"] is False
            and self._height(value) - self._height(before) >= minimum,
        )
        write_json("jump-airborne.json", airborne)
        landing_tolerance = self._float_environment(
            "OVERTE_E2E_LANDING_TOLERANCE_METERS", 0.12, 0.01, 1.0)
        landed = self.wait_until(
            f"landing within {landing_tolerance} meters of the baseline",
            lambda value: value["avatar"]["inAir"] is False
            and value["avatar"]["flying"] is False
            and abs(self._height(value) - self._height(before)) <= landing_tolerance,
        )
        write_json("jump-landed.json", landed)
        return before, airborne, landed

    def fly(self, duration_seconds: float = 2.0) -> tuple[dict, dict]:
        before = self.stable_ground_snapshot("fly-before.json")
        if before["avatar"]["flyingEnabled"] is not True:
            fail("avatar flying is not enabled")
        self._invoke("input.fly", {"durationSeconds": duration_seconds})
        minimum = self._float_environment("OVERTE_E2E_MIN_FLY_METERS", 0.5, 0.05, 20.0)
        flying = self.wait_until(
            f"active flight with a height gain of at least {minimum} meters",
            lambda value: value["avatar"]["inAir"] is True
            and value["avatar"]["flying"] is True
            and value["avatar"]["flyingEnabled"] is True
            and self._height(value) - self._height(before) >= minimum,
        )
        write_json("fly-active.json", flying)
        return before, flying

    def set_tablet(self, opened: bool) -> dict:
        before = self.snapshot("tablet-before.json")
        if before["tablet"]["open"] is not opened:
            operation_name = "tablet.open" if opened else "tablet.close"
            arguments = {"holdMilliseconds": 1000} if self.pico_openxr else None
            if self.pico_openxr:
                result = validate_operation_result(
                    operation_name, operation(operation_name, arguments))
            else:
                result = self._invoke(operation_name, {})
            write_json("tablet-open-input-result.json" if opened
                       else "tablet-close-input-result.json", result)
        after = self.wait_until(
            "tablet to open" if opened else "tablet to close",
            lambda value: value["tablet"]["open"] is opened,
        )
        write_json("tablet-open.json" if opened else "tablet-closed.json", after)
        return after

    def assert_tablet_input_isolation(self) -> tuple[dict, dict]:
        self.set_tablet(True)
        before = self.input_neutral_snapshot("tablet-isolation-before.json")
        maximum_drift = self._float_environment(
            "OVERTE_E2E_MAX_TABLET_WORLD_DRIFT_METERS", 0.08, 0.001, 1.0)
        maximum_speed = self._float_environment(
            "OVERTE_E2E_MAX_NEUTRAL_SPEED_MPS", 0.08, 0.001, 2.0)
        try:
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
        self.load_controlled_scene()
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
        before = self.ensure_controlled_scene()
        after = self.load_controlled_scene()
        if (after["scene"]["entityCount"] != before["scene"]["entityCount"]
                or not after["scene"]["spawnValidated"]):
            fail("controlled scene reload did not restore the fixture")
        write_json("scene-reloaded.json", after)
        return before, after
