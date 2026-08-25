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
REPOSITORY_ROOT = ROOT.parents[2]
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
             "arguments": {"horizontal": 0.2, "vertical": -0.1}},
            {"id": "move-forward", "operation": "input.move",
             "arguments": {"direction": "forward", "durationSeconds": 0.4}},
            {"id": "open-tablet", "operation": "tablet.open", "arguments": {}},
            {"id": "close-tablet", "operation": "tablet.close", "arguments": {}},
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
        self.assertEqual([0.0, 0.8], movement)
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
        self.assertFalse(any(active["boolean"].values()))
        self.assertFalse(any(active["float"].values()))
        self.assertTrue(all(value == [0.0, 0.0]
                            for value in active["vector2f"].values()))
        self.assertEqual({}, active["pose"])
        self.assertIn("xrLocateViews", compiled["requiredInterception"])
        self.assertNotIn("xrGetActionStateBoolean", compiled["requiredInterception"])
        self.assertNotIn("xrGetActionStateFloat", compiled["requiredInterception"])
        self.assertNotIn("xrGetActionStateVector2f", compiled["requiredInterception"])

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
        for definition in ("button", "scalar", "thumbstick", "pose"):
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])

    def test_native_layer_identity_and_release_exclusion_are_mechanical(self) -> None:
        native_root = (REPOSITORY_ROOT /
                       "android/vr/pico/apps/picoInterface/openxr/e2e_input")
        header = (native_root / "E2eInputProtocol.h").read_text(encoding="utf-8")
        protocol = (native_root / "E2eInputProtocol.cpp").read_text(encoding="utf-8")
        layer = (native_root / "XrApiLayer.cpp").read_text(encoding="utf-8")
        cmake = (native_root.parent / "CMakeLists.txt").read_text(encoding="utf-8")
        app_root = native_root.parents[1]
        gradle = (app_root / "build.gradle").read_text(encoding="utf-8")
        context = (native_root.parent / "src/OpenXrContext.cpp").read_text(encoding="utf-8")
        manifest_path = (
            app_root /
            "src/debug/assets/openxr/1/api_layers/explicit.d/overte_e2e_input.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIn(profile_fingerprint(self.profile), header)
        self.assertEqual(self.profile["profileId"], PROFILE_ID)
        self.assertEqual(profile_fingerprint(self.profile), PROFILE_SHA256)
        self.assertIn('XR_APILAYER_OVERTE_e2e_input', header)
        self.assertIn('/data/user/0/org.overte.pico/files/overte-e2e/openxr-input', header)
        for controls in self.profile["controls"].values():
            for action_name in controls.values():
                self.assertIn(f'"{action_name}"', protocol)
        self.assertNotIn('"system_click"', protocol)
        self.assertIn("XR_REFERENCE_SPACE_TYPE_STAGE", layer)
        self.assertIn('visibility("default")', layer)
        self.assertIn("xrNegotiateLoaderApiLayerInterface", layer)
        self.assertIn("if(ANDROID AND OVERTE_PICO_E2E_OPENXR_INPUT)", cmake)
        self.assertIn("arguments '-DOVERTE_PICO_E2E_OPENXR_INPUT=ON'", gradle)
        self.assertIn("arguments '-DOVERTE_PICO_E2E_OPENXR_INPUT=OFF'", gradle)
        self.assertIn("enabledApiLayerNames = &E2E_INPUT_LAYER", context)
        self.assertEqual("XR_APILAYER_OVERTE_e2e_input",
                         manifest["api_layer"]["name"])
        self.assertEqual("libXrApiLayer_overte_e2e_input.so",
                         manifest["api_layer"]["library_path"])
        release_manifest = app_root / "src/release/assets/openxr/1/api_layers/explicit.d"
        self.assertFalse(release_manifest.exists())


if __name__ == "__main__":
    unittest.main()
