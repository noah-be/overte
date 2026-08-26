#!/usr/bin/env python3
"""Device-free tests for the Pico OpenXR common-adapter session."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.device.openxr_input.adapter_session import (
    AdapterSessionError, PicoOpenXrAdapterSession, isolated_server_port,
    resolve_state_directory,
)


class FakeTransport:
    def __init__(self) -> None:
        self.envelopes: list[dict] = []
        self.cleanup_count = 0

    def stage(self, envelope, profile):
        self.envelopes.append(envelope)
        return {"sequence": envelope["sequence"]}

    def read_status(self, *, expected_nonce=None, expected_sequence=None):
        sequence = expected_sequence or len(self.envelopes)
        operation = (self.envelopes[sequence - 1]["commands"][0]["operation"]
                     if sequence else "")
        return {
            "enabled": True,
            "acceptedSequence": sequence,
            "acceptedNonce": "[redacted]",
            "state": "active" if expected_sequence is not None else "neutral",
            "viewAppliedSequence": sequence if operation == "input.look" else 0,
            "viewAppliedYawDegrees": 25.0 if operation == "input.look" else 0.0,
            "viewAppliedPitchDegrees": 0.0,
            "vectorAppliedSequence": sequence if operation == "input.move" else 0,
            "leftThumbstickAppliedY": 0.4 if operation == "input.move" else 0.0,
            "booleanAppliedSequence": sequence if (
                operation.startswith("tablet.") or
                operation in {"input.jump", "input.fly"}) else 0,
            "leftSecondaryApplied": operation.startswith("tablet."),
            "rightSecondaryApplied": operation in {"input.jump", "input.fly"},
        }

    def cleanup(self):
        self.cleanup_count += 1


class PicoOpenXrAdapterSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pico-openxr-session-")
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.transport = FakeTransport()
        self.session = PicoOpenXrAdapterSession(
            self.transport, "private-pico-selector", self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_common_operations_share_nonce_and_advance_sequence(self) -> None:
        self.session.begin("42:100")
        first = self.session.stage(
            "42:100", "input.look", {"horizontal": 0.25, "vertical": 0.0})
        second = self.session.stage(
            "42:100", "input.move",
            {"direction": "forward", "durationSeconds": 1.5})
        self.assertEqual([1, 2], [item["sequence"] for item in self.transport.envelopes])
        self.assertEqual(self.transport.envelopes[0]["sessionNonce"],
                         self.transport.envelopes[1]["sessionNonce"])
        self.assertEqual("head-pose", first["inputDomain"])
        self.assertTrue(first["viewApplied"])
        self.assertEqual(25.0, first["viewYawDegrees"])
        self.assertEqual("controller-action", second["inputDomain"])
        self.assertTrue(second["openXrVectorApplied"])
        self.assertEqual(0.4, second["openXrLeftThumbstickY"])
        serialized = str((first, second))
        self.assertNotIn(self.transport.envelopes[0]["sessionNonce"], serialized)
        self.assertNotIn("private-pico-selector", self.session.state_path.name)
        self.assertEqual(0o600, self.session.state_path.stat().st_mode & 0o777)

    def test_process_restart_fails_closed_without_rotating_nonce(self) -> None:
        self.session.begin("42:100")
        self.session.stage("42:100", "tablet.open", {})
        old_nonce = self.transport.envelopes[-1]["sessionNonce"]
        with self.assertRaisesRegex(AdapterSessionError, "identity changed"):
            self.session.stage("43:200", "tablet.close", {})
        self.assertEqual(0, self.transport.cleanup_count)
        self.assertEqual(1, self.transport.envelopes[-1]["sequence"])
        self.assertEqual(old_nonce, self.transport.envelopes[-1]["sessionNonce"])

    def test_jump_and_fly_use_right_secondary_with_one_shared_session(self) -> None:
        self.session.begin("42:100")
        jumped = self.session.stage("42:100", "input.jump", {})
        flew = self.session.stage(
            "42:100", "input.fly", {"durationSeconds": 3.0})
        self.assertEqual([1, 2], [
            envelope["sequence"] for envelope in self.transport.envelopes])
        self.assertEqual(
            self.transport.envelopes[0]["sessionNonce"],
            self.transport.envelopes[1]["sessionNonce"],
        )
        self.assertTrue(jumped["openXrBooleanApplied"])
        self.assertTrue(jumped["openXrRightSecondaryApplied"])
        self.assertTrue(flew["openXrBooleanApplied"])
        self.assertTrue(flew["openXrRightSecondaryApplied"])
        self.assertFalse(jumped["neutralBeforeCommand"])
        self.assertTrue(flew["neutralBeforeCommand"])

    def test_cleanup_is_neutral_and_idempotent(self) -> None:
        self.session.begin("42:100")
        self.session.stage("42:100", "tablet.open", {})
        self.session.cleanup(process_running=True)
        self.session.cleanup(process_running=False)
        self.assertEqual(2, self.transport.cleanup_count)
        self.assertFalse(self.session.state_path.exists())

    def test_stage_requires_the_single_launcher_session(self) -> None:
        with self.assertRaisesRegex(AdapterSessionError, "not established"):
            self.session.stage("42:100", "input.look", {})
        self.session.begin("42:100")
        self.session.require_process_identity("42:100")
        with self.assertRaisesRegex(AdapterSessionError, "identity changed"):
            self.session.require_process_identity("43:200")
        with self.assertRaisesRegex(AdapterSessionError, "already established"):
            self.session.begin("42:100")

    def test_configuration_requires_nondefault_port_and_private_directory(self) -> None:
        with mock.patch.dict(os.environ, {"ANDROID_ADB_SERVER_PORT": "5037"}, clear=True):
            with self.assertRaisesRegex(AdapterSessionError, "non-default"):
                isolated_server_port()
        insecure = self.root / "insecure"
        insecure.mkdir(mode=0o755)
        with mock.patch.dict(os.environ, {
                "OVERTE_PICO_OPENXR_STATE_DIR": str(insecure)}, clear=True):
            with self.assertRaisesRegex(AdapterSessionError, "not private"):
                resolve_state_directory()


if __name__ == "__main__":
    unittest.main()
