"""Prevent copied device outputs from satisfying independent coverage slots."""
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from device import bind_result_use


class ResultReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = self.root / "first"
        self.first.mkdir()
        self.identity = dict(contract="overte-sh004-result-v1", sourceRevision="a" * 40,
                             artifactSha256="b" * 64, runSha256="c" * 64,
                             summarySha256="d" * 64, junitSha256="e" * 64)
        (self.first / "result-identity.json").write_text(json.dumps(self.identity))
        (self.first / "run-manifest.json").write_text(json.dumps({"suite": "e2e-core"}))
        self.errors = []
        def need(value, rule, message):
            if not value:
                self.errors.append(rule)
            return bool(value)
        self.ctx = SimpleNamespace(need=need)

    def test_copy_cannot_stand_in_for_another_device(self):
        second = self.root / "second"
        shutil.copytree(self.first, second)
        self.assertTrue(bind_result_use(self.ctx, self.first, "e2e-core", "iphone"))
        self.assertFalse(bind_result_use(self.ctx, second, "e2e-core", "ipad"))
        self.assertIn("copied-device-result", self.errors)

    def test_json_reformatting_does_not_create_new_evidence(self):
        second = self.root / "second"
        shutil.copytree(self.first, second)
        (second / "result-identity.json").write_text(json.dumps(self.identity, indent=4, sort_keys=True))
        self.assertTrue(bind_result_use(self.ctx, self.first, "e2e-core", "ipad"))
        self.assertFalse(bind_result_use(self.ctx, second, "e2e-core", "ipad"))

    def test_same_result_can_be_revalidated_for_same_slot(self):
        self.assertTrue(bind_result_use(self.ctx, self.first, "e2e-core", "ipad"))
        self.assertTrue(bind_result_use(self.ctx, self.first, "e2e-core", "ipad"))
        self.assertFalse(bind_result_use(self.ctx, self.first, "e2e-core", "iphone"))

    def test_suite_alias_cannot_replace_actual_recorded_suite(self):
        self.assertFalse(bind_result_use(self.ctx, self.first, "stability", "ipad"))
        self.assertEqual(self.errors, ["device-suite-identity"])


if __name__ == "__main__":
    unittest.main()
