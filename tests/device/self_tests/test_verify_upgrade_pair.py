#!/usr/bin/env python3
"""Unit tests for monotonic real-build upgrade pair verification."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_upgrade_pair", ROOT / "verify_upgrade_pair.py")
PAIR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PAIR)


def artifact(version_code: str, version_name: str, digest: str) -> dict:
    return {
        "apk": f"overte-{version_name}.apk",
        "package": "org.overte.pico",
        "sha256": digest * 64,
        "signature_verified": True,
        "signer_certificate_sha256": "c" * 64,
        "version_code": version_code,
        "version_name": version_name,
    }


class UpgradePairTest(unittest.TestCase):
    def test_upgrade_suite_runs_install_before_the_common_smoke(self):
        catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        modules = [item for item in catalog["modules"]
                   if "update-upgrade" in item["suites"]]
        self.assertEqual(
            ["update-upgrade", "scene", "look", "move", "tablet"],
            [item["id"] for item in modules])
        self.assertTrue({"app.install", "app.stop", "app.upgrade", "app.version"}
                        .issubset(modules[0]["requires"]))

    def test_accepts_distinct_monotonic_same_signer_pair(self):
        result = PAIR.verify(
            artifact("41", "1.0.0", "a"), artifact("42", "1.0.1", "b"))
        self.assertTrue(result["upgradeReady"])
        self.assertEqual(41, result["source"]["versionCode"])
        self.assertEqual(42, result["candidate"]["versionCode"])

    def test_rejects_non_upgrade_pairs(self):
        source = artifact("41", "1.0.0", "a")
        cases = [
            artifact("41", "1.0.1", "b"),
            artifact("42", "1.0.0", "b"),
            artifact("42", "1.0.1", "a"),
        ]
        mismatched = artifact("42", "1.0.1", "b")
        mismatched["signer_certificate_sha256"] = "d" * 64
        cases.append(mismatched)
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                PAIR.verify(source, candidate)


if __name__ == "__main__":
    unittest.main()
