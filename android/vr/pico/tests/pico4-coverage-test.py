#!/usr/bin/env python3
"""Validate and summarize the risk-based Pico 4 test coverage matrix."""

from pathlib import Path
import ast
import json
import unittest


TEST_DIR = Path(__file__).resolve().parent
MATRIX = json.loads((TEST_DIR / "pico4-coverage.json").read_text(encoding="utf-8"))
RUNNER_TREE = ast.parse((TEST_DIR / "pico4-test-suite.py").read_text(encoding="utf-8"))
EXPECTED_CATALOG_CASES = 31


def catalog_entries() -> list[str]:
    names = []
    for node in ast.walk(RUNNER_TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "test":
            if node.args and isinstance(node.args[0], ast.Constant):
                names.append(node.args[0].value)
    return names


def catalog_names() -> set[str]:
    return set(catalog_entries())


def result_exit_code(result: unittest.TestResult) -> int:
    return 0 if result.wasSuccessful() else 1


class CoverageMatrixTests(unittest.TestCase):
    def test_process_exit_code_reflects_test_result(self):
        class Result:
            def __init__(self, successful):
                self.successful = successful

            def wasSuccessful(self):
                return self.successful

        self.assertEqual(result_exit_code(Result(True)), 0)
        self.assertEqual(result_exit_code(Result(False)), 1)

    def test_catalog_contains_31_unique_cases(self):
        entries = catalog_entries()
        self.assertEqual(len(entries), EXPECTED_CATALOG_CASES)
        self.assertEqual(len(set(entries)), EXPECTED_CATALOG_CASES)

    def test_every_capability_has_multiple_independent_checks(self):
        for capability in MATRIX["capabilities"]:
            self.assertGreaterEqual(len(set(capability["tests"])), 2, capability["id"])

    def test_all_matrix_tests_exist_in_suite_catalog(self):
        known = catalog_names()
        referenced = {name for item in MATRIX["capabilities"] for name in item["tests"]}
        self.assertEqual(referenced - known, set())

    def test_every_functional_suite_test_is_mapped_to_a_capability(self):
        infrastructure = {"suite-runner", "coverage-matrix", "shell-syntax"}
        known = catalog_names() - infrastructure
        referenced = {name for item in MATRIX["capabilities"] for name in item["tests"]}
        self.assertEqual(known - referenced, set())

    def test_critical_capabilities_have_at_least_two_tests(self):
        critical = [item for item in MATRIX["capabilities"] if item["risk"] == "critical"]
        self.assertGreaterEqual(len(critical), 4)
        for capability in critical:
            self.assertGreaterEqual(len(capability["tests"]), 2, capability["id"])


if __name__ == "__main__":
    result = unittest.main(exit=False)
    if result.result.wasSuccessful():
        capabilities = MATRIX["capabilities"]
        print(f"Coverage: {len(capabilities)}/{len(capabilities)} risk capabilities mapped")
    raise SystemExit(result_exit_code(result.result))
