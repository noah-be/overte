#!/usr/bin/env python3
"""Validate the truthful repository-wide interface and subsystem coverage model."""

from pathlib import Path
import json
import unittest

from run_tests import load_catalog


ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / "tests/project-coverage.json").read_text(encoding="utf-8"))
LEVELS = {"behavior", "contract", "structural"}
STATUSES = {"covered", "partial", "gap"}
EXPECTED_INTERFACES = {
    "desktop-interface", "android-phone", "android-pico", "android-quest",
    "android-legacy-interface", "android-frameplayers", "apple-launcher",
    "server-processes",
}


def registered_native_groups() -> set[str]:
    groups = set()
    for cmake in (ROOT / "tests").glob("*/CMakeLists.txt"):
        active = [line for line in cmake.read_text(encoding="utf-8").splitlines()
                  if "setup_hifi_testcase(" in line and not line.lstrip().startswith("#")]
        if active:
            groups.add(cmake.parent.name)
    return groups


class ProjectCoverageTests(unittest.TestCase):
    def setUp(self):
        self.entries = MATRIX["interfaces"] + MATRIX["areas"]

    def test_schema_and_required_interface_inventory_are_explicit(self):
        self.assertEqual(MATRIX["schemaVersion"], 2)
        identifiers = [entry["id"] for entry in MATRIX["interfaces"]]
        self.assertEqual(set(identifiers), EXPECTED_INTERFACES)
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_every_library_is_owned_exactly_once(self):
        actual = {path.relative_to(ROOT).as_posix()
                  for path in (ROOT / "libraries").iterdir() if path.is_dir()}
        mapped = [root for area in MATRIX["areas"] for root in area["roots"]
                  if root.startswith("libraries/")]
        self.assertEqual(set(mapped), actual)
        self.assertEqual(len(mapped), len(set(mapped)))

    def test_every_registered_native_group_is_mapped_exactly_once(self):
        mapped = [name for area in MATRIX["areas"] for name in area["native"]]
        self.assertEqual(set(mapped), registered_native_groups())
        self.assertEqual(len(mapped), len(set(mapped)))

    def test_evidence_references_real_catalog_suites_and_declares_strength(self):
        known = {suite.identifier for suite in load_catalog()}
        for entry in self.entries:
            self.assertIn(entry["status"], STATUSES, entry["id"])
            self.assertTrue(entry["evidence"], entry["id"])
            for evidence in entry["evidence"]:
                self.assertIn(evidence["suite"], known, entry["id"])
                self.assertIn(evidence["level"], LEVELS, entry["id"])

    def test_statuses_do_not_overstate_structural_checks(self):
        for entry in self.entries:
            levels = {evidence["level"] for evidence in entry["evidence"]}
            if entry["status"] == "covered":
                self.assertIn("behavior", levels, entry["id"])
                self.assertEqual(entry["gaps"], [], entry["id"])
            else:
                self.assertTrue(entry["gaps"], entry["id"])
            if entry["status"] == "gap":
                self.assertNotIn("behavior", levels, entry["id"])

    def test_mapped_roots_exist_and_runtime_boundaries_are_explicit(self):
        for entry in self.entries:
            self.assertTrue(entry["roots"], entry["id"])
            missing = [root for root in entry["roots"] if not (ROOT / root).is_dir()]
            self.assertEqual(missing, [], entry["id"])
        for interface in MATRIX["interfaces"]:
            self.assertTrue(interface["runtimeBoundaries"], interface["id"])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2)
    if result.result.wasSuccessful():
        print(f"Project coverage: {len(MATRIX['interfaces'])} interfaces and "
              f"{len(MATRIX['areas'])} subsystem areas mapped without overstating gaps")
