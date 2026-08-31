#!/usr/bin/env python3
"""Device-free tests for the experimental OpenXR semantic input contract."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]
OPENXR_ROOT = DEVICE_ROOT / "openxr_input"
sys.path.insert(0, str(DEVICE_ROOT))

from openxr_input.protocol import (BUILD_MARKER, CHANNEL, ContractError,  # noqa: E402
                                   PrototypeConsumer, compile_envelope,
                                   profile_fingerprint, validate_envelope,
                                   validate_profile)


NOW_MS = 2_000_000_000_000
NONCE = "a" * 64


class OpenXrInputProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile_path = OPENXR_ROOT / "profiles/pico4-overte.json"
        cls.profile = json.loads(cls.profile_path.read_text(encoding="utf-8"))
        cls.profile_hash = profile_fingerprint(cls.profile)

    def envelope(self, commands: list[dict] | None = None) -> dict:
        return {
            "schemaVersion": 1,
            "sessionNonce": NONCE,
            "sequence": 7,
            "issuedEpochMs": NOW_MS - 100,
            "commands": commands or [{
                "id": "look-right",
                "operation": "input.look",
                "arguments": {"horizontal": 0.24, "vertical": 0.0},
            }],
        }

    def grant(self) -> dict:
        return {
            "schemaVersion": 1,
            "buildMarker": BUILD_MARKER,
            "testBuild": True,
            "runtimeOptIn": True,
            "channel": CHANNEL,
            "consumer": self.profile["consumer"],
            "bindingProfileSha256": self.profile_hash,
            "sessionNonce": NONCE,
            "sequence": 7,
            "expiresEpochMs": NOW_MS + 60_000,
        }

    def compile(self, commands: list[dict] | None = None) -> dict:
        return compile_envelope(self.envelope(commands), self.grant(),
                                self.profile, NOW_MS)

    def test_profile_is_explicitly_prototype_only_and_fingerprinted(self) -> None:
        validate_profile(self.profile)
        self.assertTrue(self.profile["prototypeOnly"])
        self.assertRegex(self.profile_hash, r"^[0-9a-f]{64}$")
        changed = deepcopy(self.profile)
        changed["actions"]["tabletToggle"]["pulseMilliseconds"] += 1
        self.assertNotEqual(self.profile_hash, profile_fingerprint(changed))
        production = deepcopy(self.profile)
        production["prototypeOnly"] = False
        with self.assertRaisesRegex(ContractError, "prototypeOnly"):
            validate_profile(production)

    def test_compiles_common_operations_to_bounded_openxr_state(self) -> None:
        compiled = self.compile([
            {"id": "look-right", "operation": "input.look",
             "arguments": {"horizontal": 0.24, "vertical": -0.1,
                           "durationSeconds": 6.0}},
            {"id": "walk-forward", "operation": "input.move",
             "arguments": {"direction": "forward", "durationSeconds": 6.0,
                           "strength": 0.25}},
            {"id": "open-tablet", "operation": "tablet.open",
             "arguments": {"holdMilliseconds": 6000}},
            {"id": "close-tablet", "operation": "tablet.close",
             "arguments": {"holdMilliseconds": 6000}},
        ])
        self.assertTrue(compiled["prototypeOnly"])
        self.assertEqual("neutral-and-disabled", compiled["terminalState"])
        self.assertEqual([
            "xrCreateAction", "xrCreateReferenceSpace", "xrGetActionStateBoolean",
            "xrGetActionStateVector2f", "xrLocateSpace", "xrLocateViews", "xrSyncActions",
        ], compiled["requiredInterception"])
        self.assertEqual(["input.look", "input.move", "tablet.open", "tablet.close"],
                         [result["operation"] for result in compiled["results"]])
        self.assertEqual(False, compiled["results"][2]["precondition"]["probe.tablet.open"])
        self.assertEqual(True, compiled["results"][3]["precondition"]["probe.tablet.open"])
        self.assertEqual([0.0, 0.25], next(
            event["state"]["vector2f"]["left_thumbstick"]
            for event in compiled["events"]
            if event["state"]["vector2f"]["left_thumbstick"] != [0.0, 0.0]))
        self.assertEqual({"application.advancedMovement": True,
                          "application.dominantHand": "right",
                          "application.strafeEnabled": True},
                         compiled["results"][1]["precondition"])
        quaternion = next(
            event["state"]["viewOffset"]["orientation"]
            for event in compiled["events"]
            if event["state"]["viewOffset"]["yawDegrees"] != 0.0)
        self.assertAlmostEqual(1.0, math.sqrt(sum(value * value for value in quaternion)))
        terminal = compiled["events"][-1]["state"]
        self.assertEqual([0.0, 0.0], terminal["vector2f"]["left_thumbstick"])
        self.assertFalse(terminal["boolean"]["menu_click"])
        self.assertEqual([0.0, 0.0, 0.0, 1.0],
                         terminal["viewOffset"]["orientation"])

    def test_consumer_changes_state_only_at_sync_boundaries(self) -> None:
        compiled = self.compile([{
            "id": "walk-forward", "operation": "input.move",
            "arguments": {"direction": "forward", "durationSeconds": 0.4},
        }])
        consumer = PrototypeConsumer(compiled)
        consumer.sync_actions(100)
        first = consumer.vector2f("left_thumbstick")
        self.assertEqual([0.0, 0.8], first["currentState"])
        self.assertTrue(first["changedSinceLastSync"])
        # Queries between xrSyncActions calls must remain identical.
        self.assertEqual(first, consumer.vector2f("left_thumbstick"))
        self.assertIsNone(consumer.vector2f("unknown_action"))
        consumer.sync_actions(499)
        self.assertEqual([0.0, 0.8],
                         consumer.vector2f("left_thumbstick")["currentState"])
        consumer.sync_actions(500)
        released = consumer.vector2f("left_thumbstick")
        self.assertEqual([0.0, 0.0], released["currentState"])
        self.assertTrue(released["changedSinceLastSync"])

    def test_watchdog_and_non_monotonic_sync_fail_closed(self) -> None:
        compiled = self.compile()
        consumer = PrototypeConsumer(compiled)
        consumer.sync_actions(compiled["watchdogDeadlineMs"])
        self.assertFalse(consumer.enabled)
        self.assertEqual([0.0, 0.0, 0.0, 1.0],
                         consumer.view_offset()["orientation"])
        self.assertFalse(consumer.boolean("menu_click")["isActive"])

        consumer = PrototypeConsumer(compiled)
        consumer.sync_actions(200)
        with self.assertRaisesRegex(ContractError, "backwards"):
            consumer.sync_actions(199)
        self.assertFalse(consumer.enabled)
        self.assertEqual([0.0, 0.0],
                         consumer.vector2f("left_thumbstick")["currentState"])

    def test_consumer_rejects_replay_and_cross_session_streams(self) -> None:
        compiled = self.compile()
        with self.assertRaisesRegex(ContractError, "replayed"):
            PrototypeConsumer(compiled, last_sequence=compiled["sequence"])
        with self.assertRaisesRegex(ContractError, "different session"):
            PrototypeConsumer(compiled, expected_session_nonce="b" * 64)
        accepted = PrototypeConsumer(compiled, last_sequence=6,
                                     expected_session_nonce=NONCE)
        self.assertEqual(7, accepted.accepted_sequence)

    def test_grant_is_exact_short_lived_and_bound_to_sequence(self) -> None:
        cases = []
        expired = self.grant()
        expired["expiresEpochMs"] = NOW_MS
        cases.append(expired)
        long_lived = self.grant()
        long_lived["expiresEpochMs"] = NOW_MS + 300_001
        cases.append(long_lived)
        wrong_hash = self.grant()
        wrong_hash["bindingProfileSha256"] = "0" * 64
        cases.append(wrong_hash)
        wrong_sequence = self.grant()
        wrong_sequence["sequence"] += 1
        cases.append(wrong_sequence)
        no_opt_in = self.grant()
        no_opt_in["runtimeOptIn"] = False
        cases.append(no_opt_in)
        production = self.grant()
        production["testBuild"] = False
        cases.append(production)
        unknown = self.grant()
        unknown["unsafeFallback"] = True
        cases.append(unknown)
        for grant in cases:
            with self.subTest(grant=grant):
                with self.assertRaises(ContractError):
                    compile_envelope(self.envelope(), grant, self.profile, NOW_MS)

    def test_malformed_and_ambiguous_commands_are_rejected(self) -> None:
        cases = [
            {"id": "look", "operation": "input.look",
             "arguments": {"horizontal": 0.0}},
            {"id": "move", "operation": "input.move",
             "arguments": {"direction": "fly", "durationSeconds": 0.5}},
            {"id": "tablet", "operation": "tablet.open",
             "arguments": {"toggle": True}},
            {"id": "long-look", "operation": "input.look",
             "arguments": {"horizontal": 0.2, "durationSeconds": 8.001}},
            {"id": "long-move", "operation": "input.move",
             "arguments": {"direction": "forward", "durationSeconds": 8.001}},
            {"id": "long-tablet", "operation": "tablet.open",
             "arguments": {"holdMilliseconds": 8001}},
            {"id": "shell", "operation": "shell.exec", "arguments": {}},
        ]
        for command in cases:
            with self.subTest(command=command):
                with self.assertRaises(ContractError):
                    validate_envelope(self.envelope([command]))
        strafe = self.compile([{
            "id": "strafe-left", "operation": "input.move",
            "arguments": {"direction": "left", "durationSeconds": 0.5},
        }])
        active = next(event["state"]["vector2f"]["left_thumbstick"]
                      for event in strafe["events"]
                      if event["state"]["vector2f"]["left_thumbstick"] != [0.0, 0.0])
        self.assertEqual([-0.8, 0.0], active)

    def test_schema_files_are_parseable_and_cli_requires_explicit_opt_in(self) -> None:
        for path in sorted((OPENXR_ROOT / "schemas").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema",
                             payload["$schema"])
            self.assertFalse(payload["additionalProperties"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command_path = root / "commands.json"
            grant_path = root / "grant.json"
            command_path.write_text(json.dumps(self.envelope()), encoding="utf-8")
            grant_path.write_text(json.dumps(self.grant()), encoding="utf-8")
            command = [
                sys.executable, str(OPENXR_ROOT / "prototype.py"), "compile",
                "--profile", str(self.profile_path), "--grant", str(grant_path),
                "--commands", str(command_path), "--now-ms", str(NOW_MS),
            ]
            denied = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(2, denied.returncode)
            self.assertIn("explicit --allow-prototype", denied.stderr)
            allowed = subprocess.run([*command, "--allow-prototype"], text=True,
                                     capture_output=True, check=False)
            self.assertEqual(0, allowed.returncode, allowed.stderr)
            self.assertTrue(json.loads(allowed.stdout)["prototypeOnly"])


if __name__ == "__main__":
    unittest.main()
