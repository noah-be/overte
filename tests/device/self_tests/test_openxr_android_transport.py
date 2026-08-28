#!/usr/bin/env python3
"""Device-free tests for the private Pico OpenXR input transport."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.device.openxr_input.android_transport import (
    AndroidOpenXrTransport, BUILD_MARKER, CONSUMER, TransportError,
    PROFILE_ID, PROFILE_SHA256, profile_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1] / "openxr_input"
PROFILE = json.loads(
    (ROOT / "profiles/pico4-overte-controller.json").read_text(encoding="utf-8"))
NONCE = "d" * 64


class FakeRunner:
    def __init__(self, selector: str) -> None:
        self.selector = selector
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.status = b""

    def __call__(self, command, *, input=None, capture_output, check, timeout):
        if timeout != 20:
            raise AssertionError("controller transport must use a bounded ADB timeout")
        self.calls.append((command, input))
        if command[-1] == "devices":
            output = f"List of devices attached\n{self.selector}\tdevice\n".encode()
        elif command[-1] == "get-state":
            output = b"device\n"
        elif "cat \"$file\"" in command[-1]:
            output = self.status
        else:
            output = b""
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")


class OpenXrAndroidTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.adb = Path(self.temporary.name) / "adb"
        self.adb.write_text("mock", encoding="utf-8")
        self.selector = "pico-test-target"
        self.runner = FakeRunner(self.selector)
        self.transport = AndroidOpenXrTransport(
            self.adb, self.selector, runner=self.runner)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def envelope(self) -> dict:
        return {
            "schemaVersion": 1,
            "sessionNonce": NONCE,
            "sequence": 4,
            "commands": [{
                "id": "move-forward",
                "operation": "input.move",
                "arguments": {"direction": "forward", "durationSeconds": 0.4},
            }],
        }

    def test_stages_commands_then_exact_short_lived_grant(self) -> None:
        result = self.transport.stage(self.envelope(), PROFILE,
                                      now_ms=2_000_000_000_000, lifetime_ms=60_000)
        writes = [(command, payload) for command, payload in self.runner.calls if payload]
        self.assertEqual(2, len(writes))
        command_payload = json.loads(writes[0][1])
        grant_payload = json.loads(writes[1][1])
        self.assertEqual(self.envelope(), command_payload)
        self.assertEqual(BUILD_MARKER, grant_payload["buildMarker"])
        self.assertEqual(CONSUMER, grant_payload["consumer"])
        self.assertEqual(NONCE, grant_payload["sessionNonce"])
        self.assertEqual(4, grant_payload["sequence"])
        self.assertEqual(2_000_000_060_000, grant_payload["expiresEpochMs"])
        self.assertEqual(profile_fingerprint(PROFILE),
                         grant_payload["bindingProfileSha256"])
        self.assertEqual("[redacted]", result["sessionNonce"])
        self.assertNotIn(NONCE, json.dumps(result))
        self.assertIn("commands.json", writes[0][0][-1])
        self.assertIn("grant.json", writes[1][0][-1])
        self.assertIn(f'expected={len(writes[0][1])};', writes[0][0][-1])
        self.assertIn(f'expected={len(writes[1][1])};', writes[1][0][-1])
        self.assertIn('count="$expected"', writes[0][0][-1])
        self.assertIn('wc -c < "$temporary"', writes[0][0][-1])
        self.assertEqual(["shell", "-T"], writes[0][0][-3:-1])
        self.assertEqual([str(self.adb), "-P", "5038", "-s", self.selector],
                         writes[0][0][:5])

    def test_remote_shell_is_fixed_and_envelope_never_enters_argv(self) -> None:
        envelope = self.envelope()
        envelope["commands"][0]["id"] = "safe-identifier"
        self.transport.stage(envelope, PROFILE, now_ms=2_000_000_000_000)
        for command, payload in self.runner.calls:
            if payload:
                argv = " ".join(command)
                self.assertNotIn("safe-identifier", argv)
                self.assertNotIn(NONCE, argv)
                self.assertIn("run-as org.overte.pico", argv)
                self.assertIn("sh -c '", argv)
                self.assertNotIn("/sdcard", argv)

    def test_stage_requires_the_exact_native_profile_fingerprint(self) -> None:
        changed = deepcopy(PROFILE)
        changed["viewInjection"]["maxYawDegrees"] = 44
        with self.assertRaisesRegex(TransportError, "native Pico layer"):
            self.transport.stage(self.envelope(), changed,
                                 now_ms=2_000_000_000_000)
        self.assertFalse(any(payload for _, payload in self.runner.calls))

    def test_exclusivity_is_checked_before_any_write(self) -> None:
        class TwoDeviceRunner(FakeRunner):
            def __call__(self, command, **kwargs):
                result = super().__call__(command, **kwargs)
                if command[-1] == "devices":
                    result.stdout += b"other\tdevice\n"
                return result

        runner = TwoDeviceRunner(self.selector)
        transport = AndroidOpenXrTransport(self.adb, self.selector, runner=runner)
        with self.assertRaisesRegex(TransportError, "exactly"):
            transport.stage(self.envelope(), PROFILE, now_ms=2_000_000_000_000)
        self.assertFalse(any(payload for _, payload in runner.calls))

        class UnauthorizedRunner(FakeRunner):
            def __call__(self, command, **kwargs):
                result = super().__call__(command, **kwargs)
                if command[-1] == "devices":
                    result.stdout += b"unrelated\tunauthorized\n"
                return result

        runner = UnauthorizedRunner(self.selector)
        transport = AndroidOpenXrTransport(self.adb, self.selector, runner=runner)
        with self.assertRaisesRegex(TransportError, "exactly"):
            transport.stage(self.envelope(), PROFILE, now_ms=2_000_000_000_000)
        self.assertFalse(any(payload for _, payload in runner.calls))

    def test_status_validates_nonce_and_redacts_it(self) -> None:
        self.runner.status = json.dumps({
            "schemaVersion": 1,
            "buildMarker": BUILD_MARKER,
            "consumer": CONSUMER,
            "profileId": PROFILE_ID,
            "bindingProfileSha256": PROFILE_SHA256,
            "enabled": True,
            "acceptedSequence": 4,
            "viewAppliedSequence": 4,
            "viewAppliedYawDegrees": 25.0,
            "viewAppliedPitchDegrees": 0.0,
            "vectorAppliedSequence": 4,
            "leftThumbstickAppliedY": 0.4,
            "booleanAppliedSequence": 0,
            "leftSecondaryApplied": False,
            "rightSecondaryApplied": False,
            "acceptedNonce": NONCE,
            "activeCommandId": "move-forward",
            "state": "active",
            "detail": "command-window",
            "updatedEpochMs": 2_000_000_000_000,
        }).encode()
        status = self.transport.read_status(expected_nonce=NONCE, expected_sequence=4)
        self.assertEqual("[redacted]", status["acceptedNonce"])
        self.assertEqual(4, status["viewAppliedSequence"])
        self.assertEqual(25.0, status["viewAppliedYawDegrees"])
        self.assertEqual(0.4, status["leftThumbstickAppliedY"])
        with self.assertRaisesRegex(TransportError, "nonce"):
            self.transport.read_status(expected_nonce="e" * 64)

        invalid = json.loads(self.runner.status)
        invalid["enabled"] = 1
        self.runner.status = json.dumps(invalid).encode()
        with self.assertRaisesRegex(TransportError, "values"):
            self.transport.read_status()

        invalid = json.loads(self.runner.status)
        invalid["enabled"] = True
        invalid["viewAppliedSequence"] = 5
        self.runner.status = json.dumps(invalid).encode()
        with self.assertRaisesRegex(TransportError, "values"):
            self.transport.read_status()

    def test_cleanup_removes_only_allowlisted_private_transport_files(self) -> None:
        self.transport.cleanup()
        cleanup = self.runner.calls[-1][0]
        self.assertIn("grant.json", cleanup[-1])
        self.assertIn("commands.json", cleanup[-1])
        self.assertNotIn("status.json", cleanup[-1])
        self.assertNotIn("-rf", cleanup[-1])

    def test_timeout_is_reported_without_leaking_target_identity(self) -> None:
        def timeout_runner(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        transport = AndroidOpenXrTransport(
            self.adb, self.selector, runner=timeout_runner)
        with self.assertRaisesRegex(TransportError, "discovery timed out") as context:
            transport.require_exclusive_target()
        self.assertNotIn(self.selector, str(context.exception))

    def test_broken_write_pipe_is_redacted_and_never_commits_grant(self) -> None:
        class BrokenPipeRunner(FakeRunner):
            def __call__(self, command, **kwargs):
                if command[-3:-1] == ["shell", "-T"]:
                    self.calls.append((command, kwargs.get("input")))
                    raise BrokenPipeError("private-pipe-detail")
                return super().__call__(command, **kwargs)

        runner = BrokenPipeRunner(self.selector)
        transport = AndroidOpenXrTransport(self.adb, self.selector, runner=runner)
        with self.assertRaisesRegex(TransportError, "commands-write failed") as context:
            transport.stage(self.envelope(), PROFILE, now_ms=2_000_000_000_000)
        self.assertNotIn("private-pipe-detail", str(context.exception))
        self.assertEqual(1, sum(payload is not None for _, payload in runner.calls))


if __name__ == "__main__":
    unittest.main()
