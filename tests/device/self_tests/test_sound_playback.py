#!/usr/bin/env python3
"""Device-free positive and negative contracts for sound playback E2E."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "fixture" / "serve.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts import (load_capability_registry, validate_operation_arguments,
                       validate_probe_snapshot)  # noqa: E402


class SoundPlaybackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="overte-sound-contract-")
        ready_path = Path(cls.temporary.name) / "ready.json"
        cls.server = subprocess.Popen(
            [sys.executable, str(SERVER), "--ready-file", str(ready_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.monotonic() + 5
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not ready_path.exists():
            cls.server.terminate()
            raise RuntimeError("sound fixture server did not become ready")
        cls.ready = json.loads(ready_path.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        cls.server.communicate(timeout=5)
        cls.temporary.cleanup()

    def run_suite(
        self, *, sound_url: str | None = None, failure: str = ""
    ) -> tuple[subprocess.CompletedProcess, Path, tempfile.TemporaryDirectory]:
        temporary = tempfile.TemporaryDirectory(prefix="overte-sound-suite-")
        root = Path(temporary.name)
        environment = os.environ.copy()
        environment.update({
            "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            "OVERTE_E2E_SOUND_TIMEOUT_SECONDS": "1",
            "OVERTE_E2E_SOUND_URL": sound_url or self.ready["soundUrl"],
            "OVERTE_E2E_SOUND_COMMAND_URL": self.ready["soundCommandUrl"],
            "OVERTE_E2E_SOUND_REQUESTS_URL": self.ready["soundRequestsUrl"],
            "OVERTE_E2E_SOUND_DURATION_SECONDS": str(
                self.ready["sound"]["durationSeconds"]),
        })
        if failure:
            environment["OVERTE_MOCK_SOUND_FAILURE"] = failure
        else:
            environment.pop("OVERTE_MOCK_SOUND_FAILURE", None)
            environment["OVERTE_E2E_SOUND_TIMEOUT_SECONDS"] = "15"
        output = root / "results"
        result = subprocess.run([
            sys.executable, str(ROOT / "run.py"),
            "--adapter-manifest", str(ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(ROOT / "catalog.json"), "--suite", "sound-smoke",
            "--allow-virtual", "--require-complete", "--output-dir", str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=environment, check=False)
        return result, output, temporary

    def assert_rejected(self, *, sound_url: str | None = None,
                        failure: str = "", message: str) -> None:
        result, output, temporary = self.run_suite(sound_url=sound_url, failure=failure)
        try:
            self.assertEqual(1, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            sound = next(item for item in summary["results"]
                         if item["id"] == "sound-playback")
            self.assertEqual("failed", sound["status"])
            log = (output / "modules/sound-playback/module.log").read_text(encoding="utf-8")
            self.assertIn(message, log)
        finally:
            temporary.cleanup()

    @staticmethod
    def snapshot() -> dict:
        return {
            "schemaVersion": 1, "sampleEpochMs": 1, "sampleSequence": 1,
            "build": {"platform": "Mock", "version": "1", "date": "1970-01-01"},
            "application": {"running": True},
            "scene": {"ready": False, "entityCount": 0},
            "avatar": {
                "position": {"x": 0, "y": 1, "z": 4},
                "inAir": False, "flying": False, "flyingEnabled": True,
            },
            "view": {"orientation": {"x": 0, "y": 0, "z": 0}},
            "tablet": {"open": False},
            "sound": {
                "commandId": "sound-test", "url": "http://fixture/sound.wav",
                "commandObserved": True, "resourceReady": True,
                "durationSeconds": 2.0, "format": "wav",
                "injectorCreated": True, "started": True, "playing": True,
                "finished": False, "finishReason": "none",
            },
        }

    def test_fixture_serves_deterministic_wav_without_caching_and_reports_requests(self):
        with urlopen(self.ready["soundUrl"], timeout=2) as response:
            sound = response.read()
            self.assertEqual("audio/wav", response.headers.get_content_type())
            self.assertEqual("no-store", response.headers["Cache-Control"])
        self.assertEqual(128044, len(sound))
        self.assertEqual(self.ready["sound"]["sha256"], hashlib.sha256(sound).hexdigest())
        with self.assertRaises(HTTPError) as missing:
            urlopen(self.ready["baseUrl"] + "/audio/missing.wav", timeout=2)
        self.assertEqual(404, missing.exception.code)
        missing.exception.close()
        with urlopen(self.ready["soundRequestsUrl"], timeout=2) as response:
            requests = json.load(response)["requests"]
        self.assertIn(200, [item["status"] for item in requests])
        self.assertIn(404, [item["status"] for item in requests])

    def test_sound_operation_and_probe_contracts_reject_invalid_state(self):
        arguments = {
            "schemaVersion": 1, "commandId": "sound-test",
            "url": "http://fixture/sound.wav",
            "commandUrl": "http://fixture/sound-command.json",
        }
        self.assertEqual(arguments, validate_operation_arguments("sound.play", arguments))
        for invalid in (
                arguments | {"schemaVersion": 2},
                arguments | {"url": "file:///tmp/sound.wav"},
                arguments | {"commandUrl": "not-a-url"},
                arguments | {"extra": True}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_operation_arguments("sound.play", invalid)

        snapshot = self.snapshot()
        self.assertIs(snapshot, validate_probe_snapshot(snapshot))
        snapshot["sound"]["resourceReady"] = False
        with self.assertRaisesRegex(ValueError, "injector requires a ready resource"):
            validate_probe_snapshot(snapshot)
        snapshot = self.snapshot()
        snapshot["sound"]["finished"] = True
        with self.assertRaisesRegex(ValueError, "finished state is inconsistent"):
            validate_probe_snapshot(snapshot)

    def test_probe_uses_production_sound_and_injector_observations(self):
        registry = load_capability_registry()
        self.assertEqual("sound.play", registry["sound.play"]["operation"])
        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        for expression in (
                "SoundCache.getSound(soundState.url)",
                "Boolean(soundResource.downloaded)",
                "Number(soundResource.duration)",
                "Audio.playSound(soundResource",
                "Boolean(soundInjector.playing)",
                "else if (soundState.started)",
                "soundInjector.finished.connect"):
            self.assertIn(expression, probe)
        sound_source = (ROOT.parents[1] / "libraries/audio/src/Sound.cpp").read_text(
            encoding="utf-8")
        self.assertIn("properties = interpretAsWav(_data, outputAudioByteArray)", sound_source)
        self.assertIn("auto data = downSample(outputAudioByteArray, properties)", sound_source)
        self.assertIn("_audioData = std::move(audioData)", sound_source)
        self.assertIn("emit ready()", sound_source)

    def test_only_implemented_real_adapters_may_advertise_sound_play(self):
        android = ROOT / "adapters/android/adapter.py"
        desktop = ROOT / "adapters/desktop_oculix/adapter.py"
        appium = ROOT / "adapters/appium/adapter.py"
        for path in (ROOT / "adapters").rglob("*"):
            if (not path.is_file() or path.suffix not in {".py", ".json"}
                    or "mock" in path.parts or path in {android, desktop, appium}):
                continue
            self.assertNotIn("sound.play", path.read_text(encoding="utf-8"), str(path))
        for path in (android, desktop, appium):
            self.assertIn("sound.play", path.read_text(encoding="utf-8"))

    def test_complete_sound_suite_passes_with_independent_evidence(self):
        result, output, temporary = self.run_suite()
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(["launch-smoke", "sound-playback"],
                             [item["id"] for item in summary["results"]])
            module = output / "modules" / "sound-playback"
            metrics = json.loads((module / "metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(2, metrics["activeFreshSamples"])
            self.assertEqual(128044, metrics["requestedBytes"])
            self.assertEqual("natural", metrics["finishReason"])
            active = json.loads((module / "sound-active-samples.json")
                                .read_text(encoding="utf-8"))
            self.assertLess(active[0]["sampleSequence"], active[1]["sampleSequence"])
            self.assertTrue(all(item["sound"]["playing"] for item in active))
            state = json.loads((Path(temporary.name) / "state.json").read_text())
            self.assertEqual(1, state["launchCount"])
            self.assertFalse(state["running"])
        finally:
            temporary.cleanup()

    def test_active_samples_collected_during_evidence_phases_are_retained(self):
        result, output, temporary = self.run_suite(
            failure="end-after-two-active-samples")
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            active = json.loads((output / "modules/sound-playback/sound-active-samples.json")
                                .read_text(encoding="utf-8"))
            self.assertEqual(2, len(active))
            self.assertLess(active[0]["sampleSequence"], active[1]["sampleSequence"])
            self.assertTrue(all(item["sound"]["playing"] for item in active))
        finally:
            temporary.cleanup()

    def test_http_404_is_rejected(self):
        self.assert_rejected(
            sound_url=self.ready["baseUrl"] + "/audio/missing.wav",
            message="controlled sound request returned HTTP 404")

    def test_invalid_wav_never_becomes_a_ready_resource(self):
        self.assert_rejected(
            sound_url=self.ready["invalidSoundUrl"],
            message="decoded and usable")

    def test_resource_that_never_finishes_is_rejected(self):
        self.assert_rejected(failure="never-resource", message="decoded and usable")

    def test_injector_that_never_starts_is_rejected(self):
        self.assert_rejected(failure="injector-no-start", message="start playing")

    def test_injector_that_ends_too_early_is_rejected(self):
        self.assert_rejected(failure="early-end", message="ended unexpectedly")

    def test_process_restart_during_playback_is_rejected(self):
        self.assert_rejected(failure="process-restart", message="application process restarted")

    def test_stale_probe_samples_are_rejected(self):
        self.assert_rejected(failure="stale-probe", message="fresh sound probe sample")

    def test_inconsistent_probe_samples_are_rejected(self):
        self.assert_rejected(failure="inconsistent-probe", message="inconsistent or out of order")


if __name__ == "__main__":
    unittest.main()
