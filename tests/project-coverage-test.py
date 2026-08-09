#!/usr/bin/env python3
"""Validate the repository-wide layered coverage model against CMake tests."""

from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / "tests/project-coverage.json").read_text(encoding="utf-8"))


def registered_native_groups() -> set[str]:
    groups = set()
    for cmake in (ROOT / "tests").glob("*/CMakeLists.txt"):
        text = cmake.read_text(encoding="utf-8")
        active = [line for line in text.splitlines()
                  if "setup_hifi_testcase(" in line and not line.lstrip().startswith("#")]
        if active:
            groups.add(cmake.parent.name)
    return groups


class ProjectCoverageTests(unittest.TestCase):
    def test_every_area_has_automated_host_coverage(self):
        uncovered = [area["id"] for area in MATRIX["areas"] if not area["automated"]]
        self.assertEqual(uncovered, [])

    def test_every_registered_native_group_is_mapped(self):
        mapped = {name for area in MATRIX["areas"] for name in area["native"]}
        self.assertEqual(registered_native_groups() - mapped, set())

    def test_hardware_limits_are_explicit(self):
        hardware = {item for area in MATRIX["areas"] for item in area["hardware"]}
        self.assertEqual(hardware, {
            "audio-device-acceptance", "distributed-system-acceptance",
            "gpu-driver-acceptance", "pico4-headset-acceptance",
        })

    def test_area_identifiers_are_unique(self):
        identifiers = [area["id"] for area in MATRIX["areas"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_mapped_source_roots_exist_and_are_unique(self):
        roots = [root for area in MATRIX["areas"] for root in area["roots"]]
        self.assertEqual(len(roots), len(set(roots)))
        missing = [root for root in roots if not (ROOT / root).is_dir()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2)
    if result.result.wasSuccessful():
        areas = MATRIX["areas"]
        print(f"Project coverage: {len(areas)}/{len(areas)} areas have host automation")
