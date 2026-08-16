#!/usr/bin/env python3
"""Hermetic tests for native Apple-GPU runner classification."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos/tools/validate-apple-gpu-probe.py"
SPEC = importlib.util.spec_from_file_location("validate_apple_gpu_probe", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def probe(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "pixel_format_count": 1,
        "choose_error": 0,
        "context_error": 0,
        "context_created": True,
        "accelerated": True,
        "renderer_id": 16908288,
        "virtual_screen_count": 1,
        "gl_vendor": "Apple",
        "gl_renderer": "Apple M4",
        "gl_version": "4.1 Metal - 90.5",
        "glsl_version": "4.10",
    }
    value.update(changes)
    return value


class AppleGPUProbeValidatorTests(unittest.TestCase):
    def test_native_accelerated_apple_renderer_is_eligible(self) -> None:
        result = MODULE.classify(probe(), "arm64", "0")
        self.assertTrue(result["hardware_eligible"])
        self.assertEqual(result["classification"], "native-hardware")

    def test_translation_software_and_missing_context_are_diagnostic(self) -> None:
        cases = (
            (probe(), "arm64", "1"),
            (probe(gl_renderer="Apple Software Renderer"), "arm64", "0"),
            (probe(context_created=False), "arm64", "0"),
            (probe(accelerated=False), "arm64", "0"),
            (probe(gl_version="3.3"), "arm64", "0"),
            (probe(), "x86_64", "0"),
        )
        for payload, machine, translated in cases:
            with self.subTest(machine=machine, translated=translated, payload=payload):
                self.assertFalse(MODULE.classify(payload, machine, translated)["hardware_eligible"])

    def test_cli_is_fail_closed_and_writes_private_sanitized_result(self) -> None:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
            root = Path(directory)
            source = root / "probe.json"
            result = root / "result.json"
            source.write_text(json.dumps(probe()) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [str(TOOL), str(source), "--machine", "arm64", "--translated", "0",
                 "--result", str(result), "--require-hardware"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(result.stat().st_mode & 0o777, 0o600)
            stored = json.loads(result.read_text(encoding="utf-8"))
            self.assertNotIn("renderer_id", stored)
            source.write_text(json.dumps(probe(gl_renderer="Paravirtualized GPU")) + "\n",
                              encoding="utf-8")
            rejected = subprocess.run(
                [str(TOOL), str(source), "--machine", "arm64", "--translated", "0",
                 "--result", str(result), "--require-hardware"],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_duplicate_and_unknown_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
            path = Path(directory) / "probe.json"
            path.write_text('{"schema_version":1,"schema_version":1}\n', encoding="utf-8")
            with self.assertRaises(MODULE.ProbeError):
                MODULE.load_probe(path)
            payload = probe(secret_serial="secret")
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaises(MODULE.ProbeError):
                MODULE.load_probe(path)


if __name__ == "__main__":
    unittest.main()
