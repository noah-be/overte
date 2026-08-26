#!/usr/bin/env python3
"""Keep the published JSON Schema aligned with the fail-closed Fedora parser."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


SCHEMA = Path(__file__).resolve().parents[1] / "schemas/ios-fedora-artifact-manifest.schema.json"


class IOSArtifactSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_common_provenance_and_lifetime_are_mandatory(self):
        self.assertFalse(self.schema["additionalProperties"])
        self.assertTrue({"createdAt", "notAfter", "provenance"}.issubset(
            self.schema["required"]))
        provenance = self.schema["$defs"]["provenance"]
        self.assertFalse(provenance["additionalProperties"])
        self.assertEqual(
            {
                "repository", "repositoryId", "workflow", "reusableWorkflow",
                "ref", "runId", "runAttempt",
            },
            set(provenance["required"]),
        )
        properties = provenance["properties"]
        self.assertEqual(".github/workflows/ios-bootstrap.yml",
                         properties["workflow"]["const"])
        self.assertEqual(".github/workflows/ios-fedora-e2e-producer.yml",
                         properties["reusableWorkflow"]["const"])
        self.assertEqual("refs/heads/apple-ios", properties["ref"]["const"])

    def test_role_specific_contract_is_exclusive(self):
        overte, wda = self.schema["oneOf"]
        self.assertEqual("overte-app", overte["properties"]["kind"]["const"])
        self.assertEqual(["testBuildContractVersion"], overte["required"])
        self.assertEqual("webdriveragent", wda["properties"]["kind"]["const"])
        self.assertEqual({"toolchain", "xctest"}, set(wda["required"]))
        toolchain = self.schema["properties"]["toolchain"]["properties"]
        self.assertEqual("12.8.0", toolchain["xcuitestDriver"]["const"])
        self.assertEqual("16.8.0", toolchain["webdriverAgent"]["const"])


if __name__ == "__main__":
    unittest.main()
