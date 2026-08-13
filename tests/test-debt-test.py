#!/usr/bin/env python3
"""Keep native test debt explicit and reject assertion-free registered groups."""

from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEBT = json.loads((ROOT / "tests/test-debt.json").read_text(encoding="utf-8"))


def active_native_groups() -> dict[str, Path]:
    groups = {}
    for cmake in (ROOT / "tests").glob("*/CMakeLists.txt"):
        source = cmake.read_text(encoding="utf-8")
        active = [line for line in source.splitlines()
                  if "setup_hifi_testcase(" in line and not line.lstrip().startswith("#")]
        if active:
            groups[cmake.parent.name] = cmake.parent
    return groups


class NativeTestDebtTests(unittest.TestCase):
    def test_every_qskip_is_declared_with_a_reason(self):
        discovered = {}
        for source in (ROOT / "tests").rglob("*"):
            if source.suffix not in {".cpp", ".cc", ".h"}:
                continue
            count = len(re.findall(r"\bQSKIP\s*\(", source.read_text(
                encoding="utf-8", errors="ignore")))
            if count:
                discovered[source.relative_to(ROOT).as_posix()] = count
        declared = {entry["path"]: entry["count"] for entry in DEBT["skippedSources"]}
        self.assertEqual(declared, discovered)
        for entry in DEBT["skippedSources"]:
            self.assertGreaterEqual(len(entry["reason"]), 24, entry["path"])

    def test_disabled_suites_are_not_mistaken_for_registered_tests(self):
        registered = active_native_groups()
        for entry in DEBT["disabledSuites"]:
            path = ROOT / entry["path"]
            self.assertTrue(path.is_file(), entry["path"])
            self.assertNotIn(path.parent.name, registered)
            self.assertGreaterEqual(len(entry["reason"]), 24, entry["path"])

    def test_every_registered_native_group_contains_real_assertions(self):
        missing = []
        for name, directory in active_native_groups().items():
            sources = "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                                for path in directory.rglob("*")
                                if path.suffix in {".cpp", ".cc", ".h"})
            if not re.search(r"\b(?:QVERIFY|QCOMPARE|QTEST|QBENCHMARK)\s*\(", sources):
                missing.append(name)
        self.assertEqual(missing, [])

    def test_repaired_groups_are_registered_and_not_unconditionally_skipped(self):
        registered = active_native_groups()
        for name in ("jitter", "recording", "workload"):
            self.assertIn(name, registered)
        for relative in ("tests/jitter", "tests/recording", "tests/workload"):
            sources = "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                                for path in (ROOT / relative).rglob("*")
                                if path.suffix in {".cpp", ".h"})
            self.assertNotIn("QSKIP(", sources)


if __name__ == "__main__":
    unittest.main(verbosity=2)
