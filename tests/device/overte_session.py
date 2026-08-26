#!/usr/bin/env python3
"""Reusable, platform-neutral behavioral API for physical Overte sessions."""

from __future__ import annotations

import math
import os
import time
from typing import Callable

from contracts import (validate_operation_arguments, validate_operation_result,
                       validate_probe_snapshot)
from module_support import InfrastructureError, fail, operation, write_json


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


class OverteSession:
    def __init__(self) -> None:
        self.poll_seconds = self._float_environment(
            "OVERTE_E2E_POLL_SECONDS", 0.5, 0.05, 5.0)
        self.timeout_seconds = self._float_environment(
            "OVERTE_E2E_TIMEOUT_SECONDS", 45.0, 1.0, 600.0)
        self._last_sample_sequence: int | None = None

    @staticmethod
    def _float_environment(name: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(os.environ.get(name, str(default)))
        except ValueError:
            fail(f"{name} must be numeric")
        if not minimum <= value <= maximum:
            fail(f"{name} must be from {minimum} through {maximum}")
        return value

    @staticmethod
    def _same_scene(observed: str, expected: str) -> bool:
        return bool(observed) and observed.split("#", 1)[0] == expected.split("#", 1)[0]

    def _invoke(self, name: str, arguments: dict | None = None) -> dict:
        try:
            validated_arguments = validate_operation_arguments(name, arguments or {})
            return validate_operation_result(
                name, operation(name, validated_arguments))
        except ValueError as error:
            raise InfrastructureError(str(error)) from error

    def snapshot(self, artifact: str | None = None) -> dict:
        arguments = ({} if self._last_sample_sequence is None else
                     {"afterSampleSequence": self._last_sample_sequence})
        try:
            validate_operation_arguments("probe.snapshot", arguments)
            value = validate_probe_snapshot(operation("probe.snapshot", arguments))
        except ValueError as error:
            raise InfrastructureError(str(error)) from error
        sequence = value["sampleSequence"]
        if (self._last_sample_sequence is not None
                and sequence <= self._last_sample_sequence):
            raise InfrastructureError(
                "probe snapshot sampleSequence did not advance")
        self._last_sample_sequence = sequence
        if artifact:
            write_json(artifact, value)
        return value

    def wait_until(self, description: str, predicate: Callable[[dict], bool],
                   timeout_seconds: float | None = None) -> dict:
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = self.snapshot()
            if predicate(last):
                return last
            time.sleep(self.poll_seconds)
        if last is not None:
            write_json("last-probe.json", last)
        fail(f"timed out waiting for {description}")

    @staticmethod
    def _fixture_ready(value: dict) -> bool:
        scene = value["scene"]
        return (value["application"]["running"] is True
                and scene["ready"] is True
                and scene["spawnValidated"] is True
                and tuple(scene["fixtureMarkers"]) == FIXTURE_MARKERS
                and scene["fixtureMarkerCount"] == len(FIXTURE_MARKERS)
                and scene["floorTopY"] is not None
                and scene["collisionWall"] is not None)

    def load_scene(self, url: str) -> dict:
        result = self._invoke("scene.load", {"url": url})
        marker_verification = result.get("verification") == "fixture-markers"
        snapshot = self.wait_until(
            "the controlled scene and all fixture markers to become ready",
            lambda value: self._fixture_ready(value) and
            (marker_verification or self._same_scene(str(value["scene"]["url"]), url)),
        )
        write_json("scene-ready.json", snapshot)
        return snapshot

    def load_controlled_scene(self) -> dict:
        return self.load_scene(os.environ.get("OVERTE_E2E_SCENE_URL", ""))

    def ensure_controlled_scene(self) -> dict:
        """Reuse a ready fixture so independent modules do not restart Overte."""
        url = os.environ.get("OVERTE_E2E_SCENE_URL", "")
        try:
            validate_operation_arguments("scene.load", {"url": url})
            snapshot = self.snapshot()
        except InfrastructureError:
            snapshot = None
        except ValueError as error:
            raise InfrastructureError(str(error)) from error
        if snapshot is not None:
            embedded = url == "overte-e2e://fixture/scene"
            if (self._fixture_ready(snapshot)
                    and (embedded or self._same_scene(str(snapshot["scene"]["url"]), url))):
                write_json("scene-ready.json", snapshot)
                return snapshot
        return self.load_scene(url)

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
            snapshot = self.wait_until(
                "a stable grounded avatar",
                lambda value: not value["avatar"]["inAir"]
                and not value["avatar"]["flying"]
                and self._speed(value) <= self._float_environment(
                    "OVERTE_E2E_MAX_NEUTRAL_SPEED_MPS", 0.08, 0.001, 2.0),
            )
            write_json(artifact, snapshot)
        return snapshot

    def assert_spawn_grounded(self) -> dict:
        max_speed = self._float_environment(
            "OVERTE_E2E_MAX_NEUTRAL_SPEED_MPS", 0.08, 0.001, 2.0)
        snapshot = self.wait_until(
            "a validated grounded spawn above the fixture floor",
            lambda value: self._fixture_ready(value)
            and value["scene"]["avatarAboveFloor"] is True
            and value["scene"]["spawnLocationObserved"] is True
            and not value["avatar"]["inAir"]
            and not value["avatar"]["flying"]
            and self._speed(value) <= max_speed
            and self._height(value) >= float(value["scene"]["floorTopY"]),
        )
        write_json("spawn-grounded.json", snapshot)
        return snapshot

    def look(self, direction: str) -> tuple[dict, dict, dict]:
        if direction not in LOOK_INPUTS:
            fail("look direction is unsupported")
        horizontal, vertical, axis, sign = LOOK_INPUTS[direction]
        before = self.input_neutral_snapshot(f"look-{direction}-before.json")
        self._invoke("input.look", {"horizontal": horizontal, "vertical": vertical})
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_LOOK_DEGREES", 5.0, 0.1, 90.0)
        after = self.wait_until(
            f"view orientation to turn {direction} by at least {minimum} degrees",
            lambda value: sign * self._signed_angle_delta(
                before["view"]["orientation"], value["view"]["orientation"], axis) >= minimum,
        )
        write_json(f"look-{direction}-after.json", after)
        neutral = self.input_neutral_snapshot(f"look-{direction}-neutral.json")
        return before, after, neutral

    @staticmethod
    def movement_projection(before: dict, after: dict, direction: str) -> float:
        yaw = math.radians(float(before["avatar"]["bodyYawDegrees"]))
        forward = (-math.sin(yaw), -math.cos(yaw))
        right = (math.cos(yaw), -math.sin(yaw))
        position_before = before["avatar"]["position"]
        position_after = after["avatar"]["position"]
        displacement = (float(position_after["x"]) - float(position_before["x"]),
                        float(position_after["z"]) - float(position_before["z"]))
        axis = forward if direction in {"forward", "backward"} else right
        sign = 1.0 if direction in {"forward", "right"} else -1.0
        return sign * (displacement[0] * axis[0] + displacement[1] * axis[1])

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
        self._invoke("input.jump", {})
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_JUMP_METERS", 0.15, 0.01, 5.0)
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
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_FLY_METERS", 0.5, 0.05, 20.0)
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
            self._invoke("tablet.open" if opened else "tablet.close", {})
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
        self._invoke("input.move", {"direction": "forward", "durationSeconds": 5.0})
        after = self.input_neutral_snapshot("collision-after.json")
        minimum = self._float_environment(
            "OVERTE_E2E_MIN_COLLISION_APPROACH_METERS", 1.0, 0.1, 10.0)
        stopping_tolerance = self._float_environment(
            "OVERTE_E2E_COLLISION_STOP_TOLERANCE_METERS", 1.0, 0.05, 3.0)
        z = float(after["avatar"]["position"]["z"])
        if self.movement_projection(before, after, "forward") < minimum:
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
