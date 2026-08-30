#!/usr/bin/env python3
"""Device-free positive and negative proofs for the next portable E2E suites."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE_ROOT))

from contracts import (validate_operation_arguments, validate_probe_snapshot,
                       validate_operation_result, validate_text_snapshot)
from test_vertical_locomotion import snapshot


DOMAIN_ID = "11111111-2222-4333-8444-555555555555"
DOMAIN_MARKERS = [
    "OVERTE_E2E_DOMAIN_EAST", "OVERTE_E2E_DOMAIN_FLOOR",
    "OVERTE_E2E_DOMAIN_NORTH", "OVERTE_E2E_DOMAIN_ORIGIN",
]


class MockDomainControl(BaseHTTPRequestHandler):
    state_path = Path()
    token = "portable-suite-token"
    generation = 1
    failure = ""

    def do_POST(self) -> None:  # noqa: N802
        if (self.path != "/v1/domain-state"
                or self.headers.get("X-Overte-E2E-Token") != self.token):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        command = json.loads(self.rfile.read(length))
        action = command["action"]
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if action == "offline" and self.failure != "outage-missing":
            state["domainConnected"] = False
            state["sceneReady"] = False
        elif action == "online":
            state["domainConnected"] = True
            state["domainHost"] = "127.0.0.1"
            state["domainId"] = (
                "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
                if self.failure == "wrong-domain-after-recovery" else DOMAIN_ID)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        type(self).generation += 1
        payload = json.dumps({
            "schemaVersion": 1, "state": action,
            "generation": type(self).generation,
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args) -> None:
        pass


class NextPortableSuitesTest(unittest.TestCase):
    def test_new_operation_and_probe_contracts_are_closed(self):
        request = {"text": "Overte E2E äöüX", "backspaceCount": 1, "submit": True}
        self.assertEqual(request, validate_operation_arguments("text.type", request))
        observed_text = {
            "schemaVersion": 1, "value": "Overte E2E äöü", "focused": False,
            "keyboardVisible": False, "submittedCount": 1,
        }
        self.assertEqual(observed_text, validate_text_snapshot(observed_text))
        for mutation in (
                {**request, "extra": True},
                {**request, "text": "bad\ntext"},
                {**request, "backspaceCount": 99},
                {**request, "submit": 1}):
            with self.assertRaises(ValueError):
                validate_operation_arguments("text.type", mutation)

        probe = snapshot()
        probe["scriptedEntity"] = {
            "targetAvailable": True, "loaded": True,
            "scriptUrl": "scripted_interactable.js", "activationCount": 1,
            "state": "active", "color": {"red": 40, "green": 220, "blue": 100},
        }
        probe["peer"] = {
            "present": True, "sessionId": "controlled-peer",
            "displayName": "OVERTE_E2E_PEER", "position": {"x": 2, "y": 0, "z": 2},
            "observationCount": 3, "movementDistanceMeters": 0.5,
        }
        validate_probe_snapshot(probe)
        invalid = json.loads(json.dumps(probe))
        invalid["peer"]["displayName"] = "uncontrolled"
        with self.assertRaises(ValueError):
            validate_probe_snapshot(invalid)
        invalid = json.loads(json.dumps(probe))
        invalid["scriptedEntity"]["activationCount"] = -1
        with self.assertRaises(ValueError):
            validate_probe_snapshot(invalid)
        self.assertEqual(
            {"muted": True},
            validate_operation_arguments("audio.mute", {"muted": True}),
        )
        setting = {"settingId": "audio.warn-when-muted", "enabled": False}
        self.assertEqual(setting, validate_operation_arguments("setting.set", setting))
        render = {
            "schemaVersion": 1, "backend": "TestGPU", "hardwareAccelerated": True,
            "surfaceVisible": True, "blackFrame": False, "frameSequence": 2,
        }
        self.assertEqual(render, validate_operation_result("render.snapshot", render))
        probe["audio"] = {"muted": False}
        probe["settings"] = {"audioWarnWhenMuted": True}
        probe["render"] = {"frameCount": 2, "lastFrameEpochMs": 1000}
        validate_probe_snapshot(probe)

    def run_suite(self, suite: str, extra: dict[str, str] | None = None,
                  timeout: str = "5"):
        temporary = tempfile.TemporaryDirectory(prefix=f"overte-{suite}-")
        root = Path(temporary.name)
        output = root / "results"
        env = os.environ.copy()
        env.update({
            "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_LOCK_ROOT": str(root / "locks"),
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            "OVERTE_E2E_TIMEOUT_SECONDS": timeout,
            "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
            "OVERTE_E2E_DOMAIN_URL": "hifi://127.0.0.1:40102/0,2,4/0,0,0,1",
            "OVERTE_E2E_DOMAIN_HOST": "127.0.0.1",
            "OVERTE_E2E_DOMAIN_ID": DOMAIN_ID,
            "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(DOMAIN_MARKERS),
            "OVERTE_MOCK_E2E_DOMAIN_ID": DOMAIN_ID,
            **(extra or {}),
        })
        result = subprocess.run([
            sys.executable, str(DEVICE_ROOT / "run.py"),
            "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"),
            "--suite", suite, "--allow-virtual", "--require-complete",
            "--output-dir", str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=env, check=False)
        return temporary, root, output, result

    def assert_failure(self, suite: str, failure: str, module: str) -> None:
        temporary, _root, output, result = self.run_suite(suite, {
            "OVERTE_MOCK_E2E_FAILURES": failure,
        }, timeout="1")
        try:
            self.assertEqual(1, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            selected = next(item for item in summary["results"] if item["id"] == module)
            self.assertEqual("failed", selected["status"])
        finally:
            temporary.cleanup()

    def test_text_input_flow_and_failures(self):
        temporary, _root, output, result = self.run_suite("text-input-smoke")
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            entered = json.loads((output / "modules/text-input/text-submitted.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual("Overte E2E äöü", entered["value"])
            self.assertEqual(1, entered["submittedCount"])
        finally:
            temporary.cleanup()
        for failure in ("text-backspace-missing", "text-submit-missing",
                        "text-dismiss-missing"):
            with self.subTest(failure=failure):
                self.assert_failure("text-input-smoke", failure, "text-input")

    def test_scripted_entity_flow_and_failures(self):
        temporary, _root, output, result = self.run_suite("scripted-entity-smoke")
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            before = json.loads((output / "modules/scripted-entity/scripted-entity-before.json")
                                .read_text(encoding="utf-8"))
            after = json.loads((output / "modules/scripted-entity/scripted-entity-after.json")
                               .read_text(encoding="utf-8"))
            self.assertEqual(before["activationCount"] + 1, after["activationCount"])
            self.assertNotEqual(before["color"], after["color"])
        finally:
            temporary.cleanup()
        for failure in ("script-load-missing", "script-activation-missing",
                        "script-activation-duplicate"):
            with self.subTest(failure=failure):
                self.assert_failure("scripted-entity-smoke", failure, "scripted-entity")

    def test_multi_user_flow_and_failures(self):
        temporary, _root, output, result = self.run_suite("multi-user-smoke")
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            before = json.loads((output / "modules/multi-user/peer-before-roundtrip.json")
                                .read_text(encoding="utf-8"))
            after = json.loads((output / "modules/multi-user/peer-after-roundtrip.json")
                               .read_text(encoding="utf-8"))
            self.assertEqual(before["sessionId"], after["sessionId"])
            self.assertGreater(after["movementDistanceMeters"],
                               before["movementDistanceMeters"])
        finally:
            temporary.cleanup()
        for failure in ("peer-missing", "peer-static", "peer-session-changed"):
            with self.subTest(failure=failure):
                self.assert_failure("multi-user-smoke", failure, "multi-user")

    def run_network_suite(self, failure: str = ""):
        temporary = tempfile.TemporaryDirectory(prefix="overte-network-fault-")
        root = Path(temporary.name)
        MockDomainControl.state_path = root / "state.json"
        MockDomainControl.failure = failure
        MockDomainControl.generation = 1
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockDomainControl)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        extra = {
            "OVERTE_MOCK_E2E_STATE": str(MockDomainControl.state_path),
            "OVERTE_DEVICE_LOCK_ROOT": str(root / "locks"),
            "OVERTE_E2E_DOMAIN_CONTROL_URL":
                f"http://127.0.0.1:{server.server_address[1]}/v1/domain-state",
            "OVERTE_E2E_DOMAIN_CONTROL_TOKEN": MockDomainControl.token,
        }
        # Reuse the runner helper but keep its temporary directory alive only
        # long enough to copy all paths into this controller-owned root.
        env = os.environ.copy()
        env.update({
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            "OVERTE_E2E_TIMEOUT_SECONDS": "1" if failure else "5",
            "OVERTE_E2E_DOMAIN_URL": "hifi://127.0.0.1:40102/0,2,4/0,0,0,1",
            "OVERTE_E2E_DOMAIN_HOST": "127.0.0.1",
            "OVERTE_E2E_DOMAIN_ID": DOMAIN_ID,
            "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(DOMAIN_MARKERS),
            "OVERTE_MOCK_E2E_DOMAIN_ID": DOMAIN_ID,
            **extra,
        })
        output = root / "results"
        result = subprocess.run([
            sys.executable, str(DEVICE_ROOT / "run.py"),
            "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"),
            "--suite", "network-fault-recovery", "--allow-virtual", "--require-complete",
            "--output-dir", str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=env, check=False)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        return temporary, output, result

    def test_network_fault_recovers_and_rejects_missing_or_wrong_recovery(self):
        temporary, output, result = self.run_network_suite()
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            self.assertTrue((output / "modules/network-fault-recovery/network-disconnected.json")
                            .is_file())
            self.assertTrue((output / "modules/network-fault-recovery/network-reconnected.json")
                            .is_file())
        finally:
            temporary.cleanup()
        for failure in ("outage-missing", "wrong-domain-after-recovery"):
            with self.subTest(failure=failure):
                temporary, output, result = self.run_network_suite(failure)
                try:
                    self.assertEqual(1, result.returncode, result.stdout)
                    summary = json.loads((output / "summary.json").read_text(
                        encoding="utf-8"))
                    selected = next(item for item in summary["results"]
                                    if item["id"] == "network-fault-recovery")
                    self.assertEqual("failed", selected["status"])
                finally:
                    temporary.cleanup()

    def test_audio_controls_flow_and_failure(self):
        temporary, _root, output, result = self.run_suite("audio-controls")
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            restored = json.loads((output / "modules/audio-controls/audio-controls-restored.json")
                                  .read_text(encoding="utf-8"))
            self.assertFalse(restored["audio"]["muted"])
        finally:
            temporary.cleanup()
        self.assert_failure("audio-controls", "audio-mute-missing", "audio-controls")

    def test_settings_persistence_flow_and_failures(self):
        temporary, root, output, result = self.run_suite("settings-persistence")
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertTrue(state["audioWarnWhenMuted"])
            self.assertGreaterEqual(state["launchCount"], 3)
            self.assertTrue((output / "modules/settings-persistence/setting-restored.json")
                            .is_file())
        finally:
            temporary.cleanup()
        for failure in ("setting-set-missing", "setting-not-persisted"):
            with self.subTest(failure=failure):
                self.assert_failure(
                    "settings-persistence", failure, "settings-persistence")

    def test_lifecycle_under_load_flow_and_failures(self):
        temporary, root, output, result = self.run_suite("lifecycle-under-load")
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertTrue((output / "modules/lifecycle-under-load/lifecycle-load-after.json")
                            .is_file())
        finally:
            temporary.cleanup()
        for failure in ("lifecycle-process-restart", "lifecycle-scene-loss",
                        "lifecycle-tablet-loss", "render-stalled"):
            with self.subTest(failure=failure):
                self.assert_failure(
                    "lifecycle-under-load", failure, "lifecycle-under-load")

    def test_render_health_flow_and_failures(self):
        temporary, _root, output, result = self.run_suite("render-health")
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            native = json.loads((output / "modules/render-health/render-native.json")
                                .read_text(encoding="utf-8"))
            self.assertTrue(native["hardwareAccelerated"])
            self.assertFalse(native["blackFrame"])
        finally:
            temporary.cleanup()
        for failure in ("software-render", "hidden-surface", "black-frame",
                        "native-frame-stalled", "render-stalled"):
            with self.subTest(failure=failure):
                self.assert_failure("render-health", failure, "render-health")


if __name__ == "__main__":
    unittest.main()
