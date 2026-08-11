#!/usr/bin/env python3
"""Adversarial, isolated fixtures for the Phone coverage inventory."""

import copy
import json
import pathlib
import subprocess
import tempfile
import unittest


ANDROID_ROOT = pathlib.Path(__file__).resolve().parents[3]
REPO_ROOT = ANDROID_ROOT.parent
VALIDATOR = ANDROID_ROOT / "phone/tests/phone-test-inventory-test.py"
INVENTORY = json.loads(
    (ANDROID_ROOT / "phone/tests/phone-test-inventory.json").read_text(encoding="utf-8")
)


class PhoneInventoryAdversarialTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.inventory = copy.deepcopy(INVENTORY)
        self._write_fixture()

    def tearDown(self):
        self.temporary.cleanup()

    def _put(self, relative, content=""):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _write_fixture(self):
        catalog = {"suites": [
            {"id": suite} for suite in self.inventory["required_catalog_suites"]
        ]}
        self._put("android/common/tests/suite/catalog.json", json.dumps(catalog))
        for production in set(self.inventory["tested"]) | set(self.inventory["runtime_boundaries"]):
            self._put(production, "production fixture")
        for production, evidence in self.inventory["tested"].items():
            for path in evidence:
                existing = (self.root / path).read_text(encoding="utf-8") if (self.root / path).exists() else ""
                self._put(path, existing + "\n" + pathlib.Path(production).stem)
        for script, evidence in self.inventory["default_script_tested"].items():
            self._put("scripts/" + script, "production fixture")
            for path in evidence:
                existing = (self.root / path).read_text(encoding="utf-8") if (self.root / path).exists() else ""
                self._put(path, existing + "\n" + pathlib.Path(script).name)
        defaults = list(self.inventory["default_script_tested"]) + list(
            self.inventory["default_script_runtime_boundaries"]
        )
        quoted = ",\n".join(f'    "{item}"' for item in defaults)
        self._put(
            "scripts/+android_phoneInterface/defaultScripts.js",
            f"var PHONE_DEFAULT_SCRIPTS = [\n{quoted}\n];\n"
        )
        self._save_inventory()

    def _save_inventory(self):
        self._put("android/phone/tests/phone-test-inventory.json", json.dumps(self.inventory))

    def _run(self):
        return subprocess.run(
            [str(VALIDATOR), str(self.root)], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
        )

    def assertRejected(self, fragment):
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(fragment, result.stdout)

    def test_baseline_fixture_passes(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_new_phone_production_file_is_rejected(self):
        self._put(
            "android/phone/apps/phoneInterface/src/main/java/org/overte/phone/UnownedPolicy.java",
            "class UnownedPolicy {}"
        )
        self.assertRejected("lack test ownership")

    def test_stale_evidence_path_is_rejected(self):
        evidence = next(iter(self.inventory["tested"].values()))[0]
        (self.root / evidence).unlink()
        self.assertRejected("does not exist")

    def test_unrelated_generic_file_is_not_accepted_as_evidence(self):
        production = next(iter(self.inventory["tested"]))
        generic = "android/common/tests/generic-test.txt"
        self._put(generic, "this file exists but tests no Phone component")
        self.inventory["tested"][production] = [generic]
        self._save_inventory()
        self.assertRejected("does not reference production component")

    def test_unreviewed_runtime_boundary_is_rejected_even_with_long_reason(self):
        production = next(iter(self.inventory["tested"]))
        del self.inventory["tested"][production]
        self.inventory["runtime_boundaries"][production] = (
            "This plausible but false rationale must not bypass review or tests"
        )
        self._save_inventory()
        self.assertRejected("allowlist changed without validator review")

    def test_duplicate_default_script_is_rejected(self):
        bootstrap = self.root / "scripts/+android_phoneInterface/defaultScripts.js"
        content = bootstrap.read_text(encoding="utf-8")
        first = next(iter(self.inventory["default_script_tested"]))
        bootstrap.write_text(content.replace("];", f',\n    "{first}"\n];'), encoding="utf-8")
        self.assertRejected("contain duplicates")


if __name__ == "__main__":
    unittest.main()
