#!/usr/bin/env python3
"""Device-free tests for Pico 4 controller injection boundaries."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from tests.device.openxr_input.controller_protocol import (
    ControllerContractError, PrototypeOpenXrInputConsumer, compile_envelope,
    validate_envelope, validate_profile,
)
from tests.device.openxr_input.android_transport import (
    PROFILE_ID, PROFILE_SHA256, profile_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1] / "openxr_input"
PROFILE_PATH = ROOT / "profiles/pico4-overte-controller.json"
NONCE = "c" * 64


class OpenXrControllerProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    def envelope(self, commands: list[dict]) -> dict:
        return {
            "schemaVersion": 1,
            "sessionNonce": NONCE,
            "sequence": 9,
            "commands": commands,
        }

    def test_exact_pico_action_allowlist(self) -> None:
        validate_profile(self.profile)
        self.assertEqual("/interaction_profiles/bytedance/pico4_controller",
                         self.profile["interactionProfile"])
        self.assertEqual("view-reference-space-offset",
                         self.profile["viewInjection"]["mode"])
        changed = deepcopy(self.profile)
        changed["controls"]["buttons"]["left.system"] = "system_click"
        with self.assertRaisesRegex(ControllerContractError, "exact Pico 4 allowlist"):
            validate_profile(changed)
        aliased = deepcopy(self.profile)
        aliased["controls"]["poses"]["right.grip"] = "left_grip_pose"
        with self.assertRaisesRegex(ControllerContractError, "must not be aliased"):
            validate_profile(aliased)

    def test_compiles_buttons_sticks_trigger_grip_and_pose(self) -> None:
        compiled = compile_envelope(self.envelope([
            {"id": "press-a", "operation": "controller.button",
             "arguments": {"hand": "right", "control": "primary"}},
            {"id": "stick-left", "operation": "controller.thumbstick",
             "arguments": {"hand": "left", "x": -0.75, "y": 0.5}},
            {"id": "trigger-right", "operation": "controller.trigger",
             "arguments": {"hand": "right", "value": 0.8}},
            {"id": "grip-left", "operation": "controller.grip",
             "arguments": {"hand": "left", "value": 0.7}},
            {"id": "pose-right", "operation": "controller.pose",
             "arguments": {"hand": "right", "positionMeters": [0.3, 1.2, -0.4],
                           "orientation": [0.0, 0.0, 0.0, 1.0]}},
        ]), self.profile)
        self.assertEqual([
            "right_primary_click", "left_thumbstick", "right_trigger_value",
            "left_squeeze_value", "right_grip_pose",
        ], [result["actionName"] for result in compiled["results"]])
        self.assertEqual([
            "xrCreateAction", "xrCreateActionSpace", "xrCreateReferenceSpace",
            "xrGetActionStateBoolean", "xrGetActionStateFloat",
            "xrGetActionStatePose", "xrGetActionStateVector2f", "xrLocateSpace",
            "xrSyncActions",
        ], compiled["requiredInterception"])
        pose = next(event["state"]["pose"]["right_grip_pose"]
                    for event in compiled["events"]
                    if "right_grip_pose" in event["state"]["pose"])
        self.assertEqual("stage", pose["baseReferenceSpace"])
        self.assertEqual(["orientationTracked", "orientationValid",
                          "positionTracked", "positionValid"], pose["locationFlags"])
        terminal = compiled["events"][-1]["state"]
        self.assertEqual({}, terminal["pose"])
        self.assertFalse(any(terminal["boolean"].values()))
        self.assertFalse(any(terminal["float"].values()))

    def test_query_state_is_immutable_until_sync_and_watchdog_neutralizes(self) -> None:
        compiled = compile_envelope(self.envelope([{
            "id": "press-y", "operation": "controller.button",
            "arguments": {"hand": "left", "control": "secondary",
                          "holdMilliseconds": 120},
        }]), self.profile)
        consumer = PrototypeOpenXrInputConsumer(compiled)
        consumer.sync_actions(100)
        pressed = consumer.query("boolean", "left_secondary_click")
        self.assertTrue(pressed["currentState"])
        self.assertEqual(pressed, consumer.query("boolean", "left_secondary_click"))
        consumer.sync_actions(220)
        self.assertFalse(consumer.query("boolean", "left_secondary_click")["currentState"])
        consumer.sync_actions(compiled["watchdogDeadlineMs"])
        self.assertFalse(consumer.enabled)
        self.assertFalse(consumer.query("boolean", "left_secondary_click")["isActive"])

    def test_common_operations_compile_to_the_same_low_level_channels(self) -> None:
        compiled = compile_envelope(self.envelope([
            {"id": "look-right", "operation": "input.look",
             "arguments": {"horizontal": 0.2, "vertical": -0.1,
                           "durationSeconds": 6.0}},
            {"id": "move-forward", "operation": "input.move",
             "arguments": {"direction": "forward", "durationSeconds": 6.0,
                           "strength": 0.25}},
            {"id": "open-tablet", "operation": "tablet.open",
             "arguments": {"holdMilliseconds": 6000}},
            {"id": "close-tablet", "operation": "tablet.close",
             "arguments": {"holdMilliseconds": 6000}},
        ]), self.profile)
        self.assertEqual([
            "view-reference-space-offset", "left_thumbstick",
            "left_secondary_click", "left_secondary_click",
        ], [result["actionName"] for result in compiled["results"]])
        view = next(event["state"]["viewOffset"] for event in compiled["events"]
                    if event["state"]["viewOffset"]["active"])
        self.assertNotEqual([0.0, 0.0, 0.0, 1.0], view["orientation"])
        movement = next(event["state"]["vector2f"]["left_thumbstick"]
                        for event in compiled["events"]
                        if event["state"]["vector2f"]["left_thumbstick"] != [0.0, 0.0])
        self.assertEqual([0.0, 0.25], movement)
        self.assertEqual([
            {"startMs": 100, "endMs": 6100},
            {"startMs": 6200, "endMs": 12200},
            {"startMs": 12300, "endMs": 18300},
            {"startMs": 18400, "endMs": 24400},
        ], [result["activeWindow"] for result in compiled["results"]])
        self.assertEqual(24600, compiled["watchdogDeadlineMs"])
        self.assertEqual(
            ["head-pose", "controller-action", "controller-action", "controller-action"],
            [result["inputDomain"] for result in compiled["results"]],
        )
        self.assertEqual(
            ["probe.view.orientation", "probe.avatar.position",
             "probe.tablet.open", "probe.tablet.open"],
            [result["verification"] for result in compiled["results"]],
        )

    def test_head_look_never_injects_a_controller_action(self) -> None:
        compiled = compile_envelope(self.envelope([{
            "id": "head-look", "operation": "input.look",
            "arguments": {"horizontal": 0.2, "vertical": 0.1},
        }]), self.profile)
        active = next(event["state"] for event in compiled["events"]
                      if event["state"]["viewOffset"]["active"])
        self.assertLess(active["viewOffset"]["pitchDegrees"], 0.0)
        self.assertFalse(any(active["boolean"].values()))
        self.assertFalse(any(active["float"].values()))
        self.assertTrue(all(value == [0.0, 0.0]
                            for value in active["vector2f"].values()))
        self.assertEqual({}, active["pose"])
        self.assertIn("xrLocateViews", compiled["requiredInterception"])
        self.assertNotIn("xrGetActionStateBoolean", compiled["requiredInterception"])
        self.assertNotIn("xrGetActionStateFloat", compiled["requiredInterception"])
        self.assertNotIn("xrGetActionStateVector2f", compiled["requiredInterception"])

    def test_common_movement_supports_both_thumbstick_axes(self) -> None:
        for direction, expected in {
                "forward": [0.0, 0.5], "backward": [0.0, -0.5],
                "left": [-0.5, 0.0], "right": [0.5, 0.0]}.items():
            with self.subTest(direction=direction):
                compiled = compile_envelope(self.envelope([{
                    "id": f"move-{direction}", "operation": "input.move",
                    "arguments": {"direction": direction, "durationSeconds": 0.5,
                                  "strength": 0.5},
                }]), self.profile)
                active = next(
                    event["state"]["vector2f"]["left_thumbstick"]
                    for event in compiled["events"]
                    if event["state"]["vector2f"]["left_thumbstick"] != [0.0, 0.0]
                )
                self.assertEqual(expected, active)

    def test_jump_and_fly_map_to_bounded_right_secondary_windows(self) -> None:
        compiled = compile_envelope(self.envelope([
            {"id": "jump", "operation": "input.jump", "arguments": {}},
            {"id": "fly", "operation": "input.fly",
             "arguments": {"durationSeconds": 3.0}},
        ]), self.profile)
        self.assertEqual(
            ["right_secondary_click", "right_secondary_click"],
            [result["actionName"] for result in compiled["results"]],
        )
        self.assertEqual(
            [{"startMs": 100, "endMs": 550},
             {"startMs": 1150, "endMs": 4150}],
            [result["activeWindow"] for result in compiled["results"]],
        )
        fly_states = [
            (event["atMs"], event["state"]["boolean"]["right_secondary_click"])
            for event in compiled["events"] if event["atMs"] in {650, 1050, 1150, 4150}
        ]
        self.assertEqual(
            [(650, True), (1050, False), (1150, True), (4150, False)],
            fly_states,
        )
        self.assertEqual(
            ["probe.avatar.inAir", "probe.avatar.flying"],
            [result["verification"] for result in compiled["results"]],
        )
        active = [
            event for event in compiled["events"]
            if event["state"]["boolean"]["right_secondary_click"]
        ]
        self.assertEqual(3, len(active))
        self.assertFalse(any(compiled["events"][-1]["state"]["boolean"].values()))
        self.assertIn("xrGetActionStateBoolean", compiled["requiredInterception"])

    def test_invalid_or_unsafe_commands_fail_closed(self) -> None:
        cases = [
            {"id": "system", "operation": "controller.button",
             "arguments": {"hand": "right", "control": "menu"}},
            {"id": "raw", "operation": "openxr.call",
             "arguments": {"hand": "left", "function": "xrEndSession"}},
            {"id": "neutral", "operation": "controller.thumbstick",
             "arguments": {"hand": "left", "x": 0.0, "y": 0.0}},
            {"id": "overdrive", "operation": "controller.trigger",
             "arguments": {"hand": "left", "value": 1.1}},
            {"id": "no-op-grip", "operation": "controller.grip",
             "arguments": {"hand": "left", "value": 0.0}},
            {"id": "bad-pose", "operation": "controller.pose",
             "arguments": {"hand": "left", "positionMeters": [0, 1, 0],
                           "orientation": [0, 0, 0, 0.9]}},
            {"id": "long-look", "operation": "input.look",
             "arguments": {"horizontal": 0.2, "durationSeconds": 8.001}},
            {"id": "long-move", "operation": "input.move",
             "arguments": {"direction": "forward", "durationSeconds": 8.001}},
            {"id": "bad-jump", "operation": "input.jump",
             "arguments": {"durationSeconds": 0.1}},
            {"id": "short-fly", "operation": "input.fly",
             "arguments": {"durationSeconds": 0.499}},
            {"id": "long-fly", "operation": "input.fly",
             "arguments": {"durationSeconds": 8.001}},
            {"id": "long-tablet", "operation": "tablet.open",
             "arguments": {"holdMilliseconds": 8001}},
        ]
        for command in cases:
            with self.subTest(command=command):
                with self.assertRaises(ControllerContractError):
                    validate_envelope(self.envelope([command]), deepcopy(self.profile))

    def test_schema_is_closed_and_parseable(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/controller-command-envelope.schema.json").read_text(
                encoding="utf-8"))
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertFalse(schema["additionalProperties"])
        for definition in ("button", "scalar", "thumbstick", "pose",
                           "jump", "fly"):
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])

    def test_profile_identity_and_release_exclusion_are_mechanical(self) -> None:
        self.assertEqual(self.profile["profileId"], PROFILE_ID)
        self.assertEqual(profile_fingerprint(self.profile), PROFILE_SHA256)
        action_names = {
            action_name
            for controls in self.profile["controls"].values()
            for action_name in controls.values()
        }
        self.assertNotIn("/input/system/click", action_names)


if __name__ == "__main__":
    unittest.main()
