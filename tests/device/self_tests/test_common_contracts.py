#!/usr/bin/env python3
"""Unit tests for fail-closed portable arguments, results, and probe evidence."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE_ROOT))

from contracts import (validate_operation_arguments, validate_operation_result,
                       validate_probe_snapshot)
from test_vertical_locomotion import snapshot


class CommonContractTest(unittest.TestCase):
    def test_signed_look_and_directional_move_arguments_are_exact(self):
        self.assertEqual(
            {"horizontal": -0.25, "vertical": 0.0},
            validate_operation_arguments(
                "input.look", {"horizontal": -0.25, "vertical": 0.0}),
        )
        self.assertEqual(
            {"direction": "right", "durationSeconds": 1.5},
            validate_operation_arguments(
                "input.move", {"direction": "right", "durationSeconds": 1.5}),
        )
        for operation, arguments in (
                ("input.look", {"horizontal": 0.0, "vertical": 0.0}),
                ("input.look", {"horizontal": 2.0, "vertical": 0.0}),
                ("input.look", {"horizontal": 0.2}),
                ("input.move", {"direction": "north", "durationSeconds": 1.0}),
                ("input.move", {"direction": "forward", "durationSeconds": 0.0}),
                ("input.move", {"direction": "forward", "durationSeconds": 1.0,
                                "key": "W"})):
            with self.subTest(operation=operation, arguments=arguments):
                with self.assertRaises(ValueError):
                    validate_operation_arguments(operation, arguments)

    def test_snapshot_cursor_and_lifecycle_contracts_are_exact(self):
        self.assertEqual(
            {"afterSampleSequence": 42},
            validate_operation_arguments(
                "probe.snapshot", {"afterSampleSequence": 42}),
        )
        self.assertEqual({"stopped": True}, validate_operation_result(
            "app.stop", {"stopped": True}))
        self.assertEqual(
            {"running": False, "identity": None},
            validate_operation_result(
                "app.process", {"running": False, "identity": None}),
        )
        for arguments in ({"afterSampleSequence": 0}, {"afterSampleSequence": True},
                          {"sequence": 1}):
            with self.assertRaises(ValueError):
                validate_operation_arguments("probe.snapshot", arguments)
        for operation, result in (
                ("app.stop", {"stopped": False}),
                ("app.process", {"running": True, "identity": None}),
                ("app.process", {"running": False, "identity": "old"}),
                ("input.move", {"performed": False})):
            with self.subTest(operation=operation, result=result):
                with self.assertRaises(ValueError):
                    validate_operation_result(operation, result)

    def test_probe_v2_requires_motion_scene_tablet_and_sequence_evidence(self):
        valid = snapshot()
        self.assertIs(valid, validate_probe_snapshot(valid))
        mutations = []
        legacy_version = copy.deepcopy(valid)
        legacy_version["schemaVersion"] = 1
        mutations.append(legacy_version)
        missing_sequence = copy.deepcopy(valid)
        missing_sequence.pop("sampleSequence")
        mutations.append(missing_sequence)
        missing_velocity = copy.deepcopy(valid)
        missing_velocity["avatar"].pop("velocity")
        mutations.append(missing_velocity)
        invalid_yaw = copy.deepcopy(valid)
        invalid_yaw["avatar"]["bodyYawDegrees"] = float("nan")
        mutations.append(invalid_yaw)
        invalid_markers = copy.deepcopy(valid)
        invalid_markers["scene"]["fixtureMarkerCount"] = 4
        mutations.append(invalid_markers)
        missing_home = copy.deepcopy(valid)
        missing_home["tablet"].pop("home")
        mutations.append(missing_home)
        for invalid in mutations:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_probe_snapshot(invalid)

    def test_probe_orientation_history_is_bounded_ordered_and_current(self):
        valid = snapshot()
        valid["sampleSequence"] = 9
        valid["view"]["orientationHistory"] = [
            {"sampleSequence": 8, "orientation": {"x": 0.0, "y": -12.0, "z": 0.0}},
            {"sampleSequence": 9, "orientation": {"x": 0.0, "y": 0.0, "z": 0.0}},
        ]
        self.assertIs(valid, validate_probe_snapshot(valid))
        for history in (
                [{"sampleSequence": 10,
                  "orientation": {"x": 0.0, "y": 0.0, "z": 0.0}}],
                [{"sampleSequence": 8,
                  "orientation": {"x": 0.0, "y": 0.0, "z": 0.0}},
                 {"sampleSequence": 8,
                  "orientation": {"x": 0.0, "y": 1.0, "z": 0.0}}]):
            invalid = copy.deepcopy(valid)
            invalid["view"]["orientationHistory"] = history
            with self.assertRaisesRegex(ValueError, "orientation history sequence"):
                validate_probe_snapshot(invalid)


if __name__ == "__main__":
    unittest.main()
