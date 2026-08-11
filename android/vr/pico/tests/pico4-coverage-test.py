#!/usr/bin/env python3
"""Validate and summarize the risk-based Pico 4 test coverage matrix."""

from pathlib import Path
import ast
import json
import unittest


TEST_DIR = Path(__file__).resolve().parent
MATRIX = json.loads((TEST_DIR / "pico4-coverage.json").read_text(encoding="utf-8"))
RUNNER_TREE = ast.parse((TEST_DIR / "pico4-test-suite.py").read_text(encoding="utf-8"))


def catalog_names() -> set[str]:
    names = set()
    for node in ast.walk(RUNNER_TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "test":
            if node.args and isinstance(node.args[0], ast.Constant):
                names.add(node.args[0].value)
    return names


class CoverageMatrixTests(unittest.TestCase):
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
