#!/usr/bin/env python3
"""Device-free checks for the deterministic network fixture."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import Request, urlopen


SERVER = Path(__file__).resolve().parents[1] / "fixture" / "serve.py"


class FixtureTest(unittest.TestCase):
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
                    entities = json.load(response)["Entities"]
                    self.assertEqual(6, len(entities))
                    target = next(e for e in entities if e["name"] == "OVERTE_E2E_INTERACTABLE")
                    self.assertFalse(target["locked"], "the actual entity script must be able to edit its own state")
                    self.assertEqual(metadata["baseUrl"] + "/scripted_interactable.js", target["script"])
                    self.assertTrue(all(e["locked"] for e in entities if e is not target))
                with urlopen(Request(metadata["sceneUrl"], headers={"Host": "untrusted.invalid"}), timeout=2) as response:
                    target = next(e for e in json.load(response)["Entities"] if e["name"] == "OVERTE_E2E_INTERACTABLE")
                    self.assertTrue(target["script"].startswith(metadata["baseUrl"] + "/"))
                with urlopen(target["script"], timeout=2) as response:
                    self.assertIn(b"this.preload", response.read())
                with urlopen(metadata["probeScriptUrl"], timeout=2) as response:
                    self.assertIn(b"Test.saveObject", response.read())
            finally:
                process.terminate()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
