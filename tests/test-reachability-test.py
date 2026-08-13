#!/usr/bin/env python3
"""Prove that test sources are catalog-reachable or deliberately manual."""

from fnmatch import fnmatch
from pathlib import Path
import json
import unittest

from run_tests import load_catalog


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "tests/test-reachability.json").read_text(encoding="utf-8"))


def is_candidate(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    value = relative.as_posix()
    if any(part in {"build", ".build", "__pycache__"} for part in relative.parts):
        return False
    name = path.name
    executable_test = any(fnmatch(name, pattern) for pattern in (
        "*-test.sh", "*-test.py", "test_*.py", "*.test.js", "tst_*.qml",
    ))
    java_test = "/src/test/" in f"/{value}" and path.suffix == ".java"
    native_test = (value.startswith("tests/") and "/src/" in value
                   and path.suffix in {".cpp", ".cc"})
    apple_test = value.startswith("launchers/darwin/tests/") and path.suffix == ".m"
    mocha_test = value.startswith("tests/mocha/test/") and path.suffix == ".js"
    return executable_test or java_test or native_test or apple_test or mocha_test


def candidates() -> set[Path]:
    roots = (ROOT / "tests", ROOT / "android", ROOT / "launchers/darwin/tests")
    return {path.resolve() for root in roots for path in root.rglob("*")
            if path.is_file() and is_candidate(path)}


def catalog_seeds() -> set[Path]:
    seeds = set()
    for suite in load_catalog():
        for part in suite.command:
            if part == "{python}":
                continue
            path = (suite.cwd / part).resolve()
            if path.is_file():
                seeds.add(path)
    return seeds


def referenced_candidates(all_candidates: set[Path]) -> set[Path]:
    """Follow explicit file references and well-defined discovery runners."""
    reached = catalog_seeds()
    changed = True
    while changed:
        changed = False
        searchable = []
        for source in reached:
            try:
                searchable.append(source.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, UnicodeError):
                pass
        corpus = "\n".join(searchable)
        for candidate in all_candidates - reached:
            relative = candidate.relative_to(ROOT).as_posix()
            if candidate.name in corpus or relative in corpus:
                reached.add(candidate)
                changed = True

        # These runners intentionally use discovery/globs instead of spelling
        # out every leaf test. Keep the scope tied to each reachable runner.
        discovery_roots = {
            ROOT / "android/common/tests/suite/run-self-tests.sh":
                ROOT / "android/common/tests/suite",
            ROOT / "android/common/tests/ci/run-ci-contract-tests.sh":
                ROOT / "android/common/tests/ci",
            ROOT / "android/common/tests/docs/run-docs-contract-tests.sh":
                ROOT / "android/common/tests/docs",
            ROOT / "android/common/tests/reporting/run-summary-self-tests.sh":
                ROOT / "android/common/tests/reporting",
            ROOT / "android/common/tests/stability/run-tests.sh":
                ROOT / "android/common/tests/stability",
            ROOT / "android/common/tests/javascript/run-tests.sh":
                ROOT / "android/common/tests/javascript/test",
            ROOT / "android/common/tests/qml/run-qml-tests.sh":
                ROOT / "android/common/tests/qml",
            ROOT / "android/common/tests/qml/run-endurance-tests.sh":
                ROOT / "android/common/tests/qml_endurance",
        }
        for runner, directory in discovery_roots.items():
            if runner.resolve() in reached:
                for candidate in all_candidates:
                    if candidate == directory.resolve() or directory.resolve() in candidate.parents:
                        if candidate not in reached:
                            reached.add(candidate)
                            changed = True

    # CMake/Gradle/XCTest own their test-source discovery. Their catalogued
    # launchers are the auditable connection from source inventory to runtime.
    if (ROOT / "tests/project-native-test.sh").resolve() in reached:
        reached.update(path for path in all_candidates
                       if path.relative_to(ROOT).as_posix().startswith("tests/")
                       and path.suffix in {".cpp", ".cc"})
    if (ROOT / "android/common/tests/robolectric/run-tests.sh").resolve() in reached:
        reached.update(path for path in all_candidates if "/src/test/" in path.as_posix())
    if (ROOT / "tests/apple-launcher-test.sh").resolve() in reached:
        reached.update(path for path in all_candidates
                       if path.relative_to(ROOT).as_posix().startswith("launchers/darwin/tests/"))
    return reached


class TestReachabilityTests(unittest.TestCase):
    def test_every_discovered_test_has_an_execution_path_or_manual_owner(self):
        found = candidates()
        reached = referenced_candidates(found)
        manual = {(ROOT / entry["path"]).resolve() for entry in CONFIG["manual"]}
        compatibility = {(ROOT / path).resolve()
                         for path in CONFIG["compatibilityEntrypoints"]}
        unreachable = sorted(path.relative_to(ROOT).as_posix()
                             for path in found - reached - manual - compatibility)
        self.assertEqual(unreachable, [])

    def test_exceptions_are_existing_unique_tests_with_a_reason(self):
        paths = [entry["path"] for entry in CONFIG["manual"]]
        self.assertEqual(len(paths), len(set(paths)))
        for entry in CONFIG["manual"]:
            path = ROOT / entry["path"]
            self.assertTrue(path.is_file(), entry["path"])
            self.assertTrue(is_candidate(path), entry["path"])
            self.assertGreaterEqual(len(entry["reason"]), 24, entry["path"])

    def test_compatibility_entrypoints_delegate_to_a_catalogued_runner(self):
        for relative in CONFIG["compatibilityEntrypoints"]:
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertRegex(source, r"catalog[.]json|run[_-]tests|pico4-test-suite",
                             relative)

    def test_catalog_commands_are_repository_local_when_they_are_paths(self):
        for suite in load_catalog():
            for part in suite.command:
                path = (suite.cwd / part).resolve()
                if path.is_file():
                    self.assertTrue(path.is_relative_to(ROOT), suite.identifier)


if __name__ == "__main__":
    unittest.main(verbosity=2)
