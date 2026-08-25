#!/usr/bin/env python3
"""Reusable, platform-neutral behavioral API for physical Overte sessions."""

from __future__ import annotations

import math
import os
import time
from typing import Callable

from contracts import validate_probe_snapshot
from module_support import InfrastructureError, fail, operation, write_json


class OverteSession:
    def __init__(self) -> None:
        self.poll_seconds = self._float_environment("OVERTE_E2E_POLL_SECONDS", 0.5, 0.05, 5.0)
        self.timeout_seconds = self._float_environment("OVERTE_E2E_TIMEOUT_SECONDS", 45.0, 1.0, 600.0)
        self.pico_openxr = os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1"
        self.last_sample_sequence: int | None = None

    @staticmethod
    def _float_environment(name: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(os.environ.get(name, str(default)))
        except ValueError:
            fail(f"{name} must be numeric")
        if not minimum <= value <= maximum:
            fail(f"{name} must be from {minimum} through {maximum}")
        return value

    def snapshot(self, artifact: str | None = None) -> dict:
        arguments = {}
        if self.pico_openxr and self.last_sample_sequence is not None:
            arguments["afterSampleSequence"] = self.last_sample_sequence
        try:
            value = validate_probe_snapshot(operation("probe.snapshot", arguments))
        except ValueError as error:
            fail(str(error))
        if self.pico_openxr:
            sequence = value.get("sampleSequence")
            if (not isinstance(sequence, int) or isinstance(sequence, bool)
                    or sequence <= 0):
                fail("Pico probe snapshot requires a positive sampleSequence")
            if (self.last_sample_sequence is not None
                    and sequence <= self.last_sample_sequence):
                fail("Pico probe snapshot did not advance")
            self.last_sample_sequence = sequence
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
        if not url or "://" not in url:
            fail("OVERTE_E2E_SCENE_URL must be an absolute URL")
        result = operation("scene.load", {"url": url})
        expected = url.split("#", 1)[0]
        marker_verification = result.get("verification") == "fixture-markers"
        snapshot = self.wait_until(
            "the controlled scene to become ready",
            lambda value: value["scene"]["ready"] is True and
            (value["scene"].get("fixtureMarkerCount") == 4 if marker_verification else
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
        if scene.get("fixtureMarkerCount") != 4:
            fail("Pico fixture did not expose all four markers")
        if (not isinstance(scene.get("floorTopY"), (int, float))
                or abs(float(scene["floorTopY"])) > 0.02):
            fail("Pico fixture floor top is not y=0")
        if scene.get("spawnValidated") is not True:
            fail("Pico fixture spawn was not validated")
        expected = {"x": 0.0, "y": 2.0, "z": 4.0}
        spawn_tolerance = self._float_environment(
            "OVERTE_E2E_SPAWN_TOLERANCE_METERS", 0.75, 0.05, 5.0)
        if self._distance(position, expected) > spawn_tolerance:
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
            if (scene["ready"] is True
                    and (scene.get("fixtureMarkerCount") == 4 if embedded else
                         self._same_scene(str(scene.get("url", "")), expected))):
                write_json("scene-ready.json", snapshot)
                return snapshot
        return self.load_scene(url)

    @staticmethod
    def _same_scene(observed: str, expected: str) -> bool:
        if not observed:
            return False
        observed = observed.split("#", 1)[0]
        return observed == expected

    @staticmethod
    def _angle_delta(first: dict, second: dict) -> float:
        def wrapped(left: float, right: float) -> float:
            return abs((right - left + 180.0) % 360.0 - 180.0)
        return math.sqrt(sum(wrapped(float(first[axis]), float(second[axis])) ** 2
                             for axis in ("x", "y", "z")))

    def look(self, horizontal: float = 0.25, vertical: float = 0.0) -> tuple[dict, dict]:
        before = self.snapshot("look-before.json")
        result = operation("input.look", {"horizontal": horizontal, "vertical": vertical})
        write_json("look-input-result.json", result)
        minimum = self._float_environment("OVERTE_E2E_MIN_LOOK_DEGREES", 5.0, 0.1, 180.0)
        pico = self.pico_openxr

        def changed_with_neutral_controller(value: dict) -> bool:
            changed = self._angle_delta(before["view"]["orientation"],
                                        value["view"]["orientation"]) >= minimum
            if not pico:
                return changed
            controller = value.get("controller", {})
            axes = controller.get("axes", {})
            openxr = controller.get("route", {}).get("openxrAxes")
            standard_neutral = all(abs(float(axes.get(axis, 1.0))) <= 0.05
                                   for axis in ("lx", "ly", "rx", "ry"))
            openxr_neutral = isinstance(openxr, dict) and all(
                abs(float(openxr.get(axis, 1.0))) <= 0.05
                for axis in ("lx", "ly", "rx", "ry"))
            return changed and standard_neutral and openxr_neutral

        after = self.wait_until(
            f"view orientation to change by at least {minimum} degrees",
            changed_with_neutral_controller,
        )
        write_json("look-after.json", after)
        return before, after

    @staticmethod
    def _distance(first: dict, second: dict) -> float:
        return math.sqrt(sum((float(second[axis]) - float(first[axis])) ** 2
                             for axis in ("x", "y", "z")))

    def stable_avatar_snapshot(self) -> dict:
        previous = self.snapshot()
        stable_samples = 0
        tolerance = self._float_environment(
            "OVERTE_E2E_MAX_BASELINE_DRIFT_METERS", 0.03, 0.001, 1.0)

        def stable(value: dict) -> bool:
            nonlocal previous, stable_samples
            drift = self._distance(previous["avatar"]["position"],
                                   value["avatar"]["position"])
            stable_samples = stable_samples + 1 if drift <= tolerance else 0
            previous = value
            return stable_samples >= 2

        snapshot = self.wait_until("the avatar position baseline to stabilize", stable)
        write_json("move-before.json", snapshot)
        return snapshot

    def move(self, direction: str = "forward", duration_seconds: float = 1.5) -> tuple[dict, dict]:
        if direction not in {"forward", "backward", "left", "right"}:
            fail("movement direction is unsupported")
        before = self.stable_avatar_snapshot()
        pico = os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1"
        if pico:
            input_state = before.get("input", {})
            if input_state.get("dominantHand") != "right":
                fail("Pico movement requires effective right-hand dominance")
            if input_state.get("advancedMovementControls") is not True:
                fail("Pico movement requires effective advanced movement controls")
        result = operation(
            "input.move", {"direction": direction, "durationSeconds": duration_seconds})
        write_json("move-input-result.json", result)
        if pico:
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
                signs = [float(item) > 0.0 for item in values]
                return len(set(signs)) == 1

            route_snapshot = self.wait_until(
                "the complete Pico movement route to become active", complete_route)
            write_json("move-route-active.json", route_snapshot)
        minimum = self._float_environment("OVERTE_E2E_MIN_MOVE_METERS", 0.2, 0.01, 20.0)
        after = self.wait_until(
            f"avatar position to change by at least {minimum} meters",
            lambda value: self._distance(before["avatar"]["position"],
                                         value["avatar"]["position"]) >= minimum,
        )
        write_json("move-after.json", after)
        return before, after

    def set_tablet(self, opened: bool) -> dict:
        before = self.snapshot("tablet-before.json")
        if before["tablet"]["open"] is not opened:
            operation_name = "tablet.open" if opened else "tablet.close"
            result = operation(operation_name)
            write_json("tablet-open-input-result.json" if opened
                       else "tablet-close-input-result.json", result)
        after = self.wait_until(
            "tablet to open" if opened else "tablet to close",
            lambda value: value["tablet"]["open"] is opened,
        )
        write_json("tablet-open.json" if opened else "tablet-closed.json", after)
        return after
