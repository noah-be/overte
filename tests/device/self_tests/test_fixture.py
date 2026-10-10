#!/usr/bin/env python3
"""Device-free checks for the deterministic network fixture."""

from __future__ import annotations

import json
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from urllib.request import urlopen


SERVER = Path(__file__).resolve().parents[1] / "fixture" / "serve.py"


class FixtureTest(unittest.TestCase):
    def test_session_sound_duration_matches_actual_wav_and_preserves_default(self):
        base = SERVER.parent / "audio/overte-e2e-tone.wav"
        original = base.read_bytes()
        with tempfile.TemporaryDirectory(prefix="overte-sound-duration-test-") as temporary:
            ready = Path(temporary) / "ready.json"
            process = subprocess.Popen([
                sys.executable, str(SERVER), "--ready-file", str(ready),
                "--sound-duration-seconds", "30"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "sound fixture did not become ready")
                metadata = json.loads(ready.read_text())
                with urlopen(metadata["soundUrl"], timeout=2) as response:
                    self.assertEqual("audio/wav", response.headers["Content-Type"])
                    content = response.read()
                self.assertEqual(metadata["sound"]["sha256"], hashlib.sha256(content).hexdigest())
                with wave.open(io.BytesIO(content)) as decoded:
                    self.assertEqual(1, decoded.getnchannels())
                    self.assertEqual(2, decoded.getsampwidth())
                    self.assertEqual(30.0, decoded.getnframes() / decoded.getframerate())
                self.assertEqual(30.0, metadata["sound"]["durationSeconds"])
                self.assertEqual(original, base.read_bytes())
            finally:
                process.terminate()
                process.communicate(timeout=5)

    def test_session_sound_duration_rejects_unbounded_or_nonfinite_values(self):
        for value in ["0", "121", "nan", "inf"]:
            with self.subTest(value=value):
                result = subprocess.run([
                    sys.executable, str(SERVER), "--sound-duration-seconds", value],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(2, result.returncode)

    def test_fixture_contract_and_ephemeral_http_server(self):
        checked = subprocess.run(
            [sys.executable, str(SERVER), "--check"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(0, checked.returncode, checked.stdout)
        with tempfile.TemporaryDirectory(prefix="overte-fixture-test-") as temporary:
            ready = Path(temporary) / "ready.json"
            process = subprocess.Popen(
                [sys.executable, str(SERVER), "--ready-file", str(ready)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "fixture server did not become ready")
                metadata = json.loads(ready.read_text(encoding="utf-8"))
                with urlopen(metadata["baseUrl"] + "/healthz", timeout=2) as response:
                    self.assertTrue(json.load(response)["ready"])
                with urlopen(metadata["sceneUrl"], timeout=2) as response:
                    self.assertEqual(6, len(json.load(response)["Entities"]))
                with urlopen(metadata["probeScriptUrl"], timeout=2) as response:
                    self.assertIn(b"Test.saveObject", response.read())
            finally:
                process.terminate()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
