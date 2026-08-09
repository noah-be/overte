#!/usr/bin/env python3
"""Regression tests for bounded Pico shader build parallelism."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SHADERGEN = ROOT / "tools/shadergen.py"
BUILD_SCRIPT = (ROOT / "android/build-pico.sh").read_text(encoding="utf-8")


class ShadergenJobTests(unittest.TestCase):
    def run_empty(self, env=None, *extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / "commands.txt"
            commands.write_text("", encoding="utf-8")
            variables = os.environ.copy()
            variables.update(env or {})
            return subprocess.run([
                sys.executable, str(SHADERGEN), "--commands", str(commands),
                "--build-dir", str(root), "--source-dir", str(ROOT), *extra,
            ], text=True, capture_output=True, env=variables, check=False)

    def test_explicit_worker_limit_is_used(self):
        result = self.run_empty(None, "--jobs", "3", "--verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Using 3 shader worker(s)", result.stdout)

    def test_environment_worker_limit_is_used(self):
        result = self.run_empty({"SHADERGEN_JOBS": "2"}, "--verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Using 2 shader worker(s)", result.stdout)

    def test_non_positive_worker_limit_is_rejected(self):
        result = self.run_empty(None, "--jobs", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobs must be positive", result.stderr)

    def test_pico_build_forwards_its_job_limit(self):
        self.assertIn('SHADERGEN_JOBS="${PICO_SHADER_JOBS:-$jobs}"', BUILD_SCRIPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
