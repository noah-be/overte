#!/usr/bin/env python3
"""Black-box checks for the Pico 4 suite CLI."""

from pathlib import Path
import subprocess
import sys
import unittest


RUNNER = Path(__file__).with_name("pico4-test-suite.py")


class SuiteCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(RUNNER), *arguments], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_catalog_names_are_unique_and_cover_core_categories(self):
        result = self.run_cli("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [line.split() for line in result.stdout.splitlines()]
        names = [row[0] for row in rows]
        categories = {row[1] for row in rows}
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"android", "audio", "openxr", "webview", "interaction", "world"} <= categories)
        self.assertGreaterEqual(len(names), 20)

    def test_category_filter_is_exact(self):
        result = self.run_cli("--list", "--category", "openxr")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(len(result.stdout.splitlines()), 3)
        self.assertTrue(all(line.split()[1] == "openxr" for line in result.stdout.splitlines()))

    def test_unknown_selection_fails_with_usage_error(self):
        result = self.run_cli("--list", "--test", "does-not-exist")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown tests", result.stderr)

    def test_nonpositive_timeout_is_rejected(self):
        result = self.run_cli("--timeout", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be positive", result.stderr)


if __name__ == "__main__":
    unittest.main()
