#!/usr/bin/env python3
"""Closed diagnostic events must not satisfy existing runtime evidence consumers."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


def original(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ios/tools" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DiagnosticEvidenceSeparation(unittest.TestCase):
    def test_closed_events_are_not_entity_evidence(self):
        validator = original("ios_original_entity_validator", "validate-entity-gate-log.py")
        for lines in ([], ["OVT_CONNECTION_READY"], ["OVT_REDACTED"] * 6,
                      ["Overte OVT_CONNECTION_READY", "Overte OVT_REDACTED"] * 8):
            with self.subTest(lines=lines):
                result = validator.validate(lines)
                self.assertFalse(result["accepted"])
                self.assertEqual(result["completed_gates"], [])
                self.assertEqual(result["evidence"], [])
                self.assertTrue(result["errors"])

    def test_closed_events_are_not_world_navigation_or_render_evidence(self):
        validator = original("ios_original_world_validator", "validate-world-runtime.py")
        lines = ["OVT_CONNECTION_READY", "OVT_REDACTED"] * 8
        for scenario, destination in (("serverless", "file:///fixture-only.json"),
                                      ("online", "hifi://fixture.invalid")):
            with self.subTest(scenario=scenario):
                with self.assertRaisesRegex(ValueError, "navigation request marker"):
                    validator.require_navigation(lines, scenario, destination)
        with self.assertRaisesRegex(ValueError, "missing serverless runtime gate"):
            validator.validate_serverless_gates(lines, -1, "file:///fixture-only.json")


if __name__ == "__main__":
    unittest.main()
