#!/usr/bin/env python3
"""Device-free checks for the deterministic network fixture."""

from __future__ import annotations

import json
import importlib.util
from unittest.mock import patch
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen


SERVER = Path(__file__).resolve().parents[1] / "fixture" / "serve.py"


class FixtureTest(unittest.TestCase):
    def test_spawn_requires_support_at_the_actual_floor_surface(self):
        spec = importlib.util.spec_from_file_location("ground_fixture", SERVER)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        with patch.object(sys, "path", [str(SERVER.parent)] + sys.path):
            manifest = fixture.validate_fixture()
        self.assertEqual(0, manifest["spawnPosition"]["y"])
        for position in ({"x": 0, "y": 2, "z": 4},
                         {"x": 0, "y": -1, "z": 4},
                         {"x": 20, "y": 0, "z": 4}):
            invalid = json.loads(json.dumps(manifest))
            invalid["spawnPosition"] = position
            invalid["spawnPath"] = "/{x},{y},{z}/0,0,0,1".format(**position)
            scene = json.loads((SERVER.parent / "scene.json").read_text())
            scene["Paths"]["/"] = invalid["spawnPath"]
            original = Path.read_text
            def read(path, *args, **kwargs):
                if path == SERVER.parent / "fixture-manifest.json": return json.dumps(invalid)
                if path == SERVER.parent / "scene.json": return json.dumps(scene)
                return original(path, *args, **kwargs)
            with self.subTest(position=position), patch.object(Path, "read_text", read):
                with self.assertRaisesRegex(ValueError, "floor"):
                    fixture.validate_fixture()

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
