#!/usr/bin/env python3
"""Behavior tests for native gcov aggregation."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("generate-native-coverage.py")
WRAPPER = Path(__file__).with_name("project-native-coverage.sh")
SPEC = spec_from_file_location("native_coverage", SCRIPT)
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NativeCoverageTests(unittest.TestCase):
    def test_wrapper_help_and_non_coverage_build_validation(self):
        help_result = subprocess.run([str(WRAPPER), "--help"], text=True,
                                     capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Usage:", help_result.stdout)
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            (build / "CMakeCache.txt").write_text(
                "CMAKE_CXX_FLAGS_DEBUG:STRING=-O0 -g\n", encoding="utf-8")
            result = subprocess.run([str(WRAPPER), str(build)], text=True,
                                    capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not configured with --coverage", result.stderr)

    def test_duplicate_objects_merge_counts_and_ignore_external_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "libraries/shared/src/Value.cpp"
            external = Path("/usr/include/value.h")
            documents = [
                {"files": [{"file": str(source), "lines": [
                    {"line_number": 10, "count": 0, "branches": [{"count": 0}]},
                    {"line_number": 11, "count": 2, "branches": []}],
                    "functions": [{"name": "value", "start_line": 10, "execution_count": 0}]}]},
                {"files": [{"file": str(source), "lines": [
                    {"line_number": 10, "count": 3, "branches": [{"count": 1}]}],
                    "functions": [{"name": "value", "start_line": 10, "execution_count": 1}]},
                    {"file": str(external), "lines": [{"line_number": 1, "count": 1}],
                     "functions": []}]},
            ]
            report = MODULE.merge_documents(documents, root)
        self.assertEqual(len(report["files"]), 1)
        self.assertEqual(report["summary"]["lines"], {"covered": 2, "total": 2, "percent": 100.0})
        self.assertEqual(report["summary"]["functions"]["covered"], 1)
        self.assertEqual(report["summary"]["branches"]["covered"], 1)
        self.assertEqual(report["components"][0]["path"], "libraries/shared")
        self.assertEqual(report["files"][0]["line_hits"], {"10": 3, "11": 2})

    def test_changed_line_parser_and_diff_summary(self):
        diff = """+++ b/libraries/shared/src/Value.cpp
@@ -9,0 +10,2 @@
+one
+two
"""
        changed = MODULE.parse_changed_lines(diff)
        self.assertEqual(changed["libraries/shared/src/Value.cpp"], {10, 11})
        report = {"files": [{"path": "libraries/shared/src/Value.cpp",
                             "line_hits": {"10": 0, "11": 4}}]}
        self.assertEqual(MODULE.diff_summary(report, changed),
                         {"covered": 1, "total": 2, "percent": 50.0})

    def test_zero_total_percentage_is_well_defined(self):
        report = MODULE.merge_documents([], Path("/tmp/not-used"))
        self.assertEqual(report["summary"]["lines"]["percent"], 0.0)
        self.assertEqual(report["files"], [])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "index.html"
            MODULE.write_html(report, output)
            self.assertIn("Lines: 0.00% (0/0)", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
