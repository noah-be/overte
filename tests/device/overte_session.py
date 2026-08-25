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
        try:
            value = validate_probe_snapshot(operation("probe.snapshot"))
        except ValueError as error:
            fail(str(error))
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
        operation("input.look", {"horizontal": horizontal, "vertical": vertical})
        minimum = self._float_environment("OVERTE_E2E_MIN_LOOK_DEGREES", 5.0, 0.1, 180.0)
        after = self.wait_until(
            f"view orientation to change by at least {minimum} degrees",
            lambda value: self._angle_delta(before["view"]["orientation"],
                                             value["view"]["orientation"]) >= minimum,
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
        operation("input.move", {"direction": direction, "durationSeconds": duration_seconds})
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
            operation("tablet.open" if opened else "tablet.close")
        after = self.wait_until(
            "tablet to open" if opened else "tablet to close",
            lambda value: value["tablet"]["open"] is opened,
        )
        write_json("tablet-open.json" if opened else "tablet-closed.json", after)
        return after
