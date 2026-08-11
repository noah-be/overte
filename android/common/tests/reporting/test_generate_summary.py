import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import generate_summary as summary


class SummaryTest(unittest.TestCase):
    def test_pass_fail_skip_and_coverage_and_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "junit.xml").write_text(
                '<testsuite tests="5" failures="1" errors="1" skipped="1"/>')
            (root / "jacoco.xml").write_text(
                '<?xml version="1.0"?><!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">'
                '<report><counter type="LINE" missed="1" covered="9"/>'
                '<counter type="BRANCH" missed="2" covered="8"/></report>')
            (root / "coverage.json").write_text(json.dumps({
                "total": {"lines": {"covered": 7, "total": 8},
                          "branches": {"covered": 3, "total": 4}}}))
            (root / "mutation.json").write_text(json.dumps({
                "mode": "quick", "killed": 3, "survived": 1, "errors": 0,
                "mutants": [{}, {}, {}, {}]}))
            console, markdown, issues = summary.generate(
                [f"suite={root / 'junit.xml'}"],
                [f"jvm={root / 'jacoco.xml'}", f"js={root / 'coverage.json'}"],
                [f"critical={root / 'mutation.json'}"])
        self.assertEqual(0, issues)
        self.assertIn("2 passed, 2 failed, 1 skipped / 5", console)
        self.assertIn("line 90.00% (9/10)", markdown)
        self.assertIn("3/4 killed, 1 survived", markdown)

    def test_missing_and_malformed_are_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broken = root / "broken.xml"
            broken.write_text("<not-closed", encoding="utf-8")
            console, markdown, issues = summary.generate(
                [f"missing={root / 'missing.xml'}", f"broken={broken}"], [], [])
        self.assertEqual(2, issues)
        self.assertIn("MISSING", console)
        self.assertIn("MALFORMED", console)
        self.assertIn("Report issues", markdown)

    def test_junit_glob_aggregates_robolectric_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TEST-one.xml").write_text('<testsuite tests="2" failures="0"/>')
            (root / "TEST-two.xml").write_text('<testsuite tests="3" failures="1" skipped="1"/>')
            console, _, issues = summary.generate([f"robo={root}/TEST-*.xml"], [], [])
        self.assertEqual(0, issues)
        self.assertIn("3 passed, 1 failed, 1 skipped / 5", console)

    def test_zero_test_junit_is_a_malformed_report_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "empty.xml"
            report.write_text(
                '<testsuite tests="0" failures="0" errors="0" skipped="0"/>',
                encoding="utf-8")
            console, markdown, issues = summary.generate([f"empty={report}"], [], [])
        self.assertEqual(1, issues)
        self.assertIn("JUnit empty: MALFORMED", console)
        self.assertIn("JUnit report contains no tests", console)
        self.assertIn("MALFORMED", markdown)

    def test_positive_junit_and_inconsistent_zero_counter_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            normal = root / "normal.xml"
            normal.write_text('<testsuite tests="1" failures="0"/>', encoding="utf-8")
            inconsistent = root / "inconsistent.xml"
            inconsistent.write_text('<testsuite tests="0" failures="1"/>', encoding="utf-8")
            self.assertEqual(1, summary.junit(normal)["passed"])
            with self.assertRaisesRegex(ValueError, "counters are inconsistent"):
                summary.junit(inconsistent)

    def test_node_native_direct_testcases_are_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "node.xml"
            report.write_text('<testsuites><testcase name="pass"/>'
                              '<testcase name="fail"><failure/></testcase>'
                              '<testcase name="skip"><skipped/></testcase></testsuites>',
                              encoding="utf-8")
            console, _, issues = summary.generate([f"node={report}"], [], [])
        self.assertEqual(0, issues)
        self.assertIn("1 passed, 1 failed, 1 skipped / 3", console)

    def test_rejects_dtd_symlink_large_and_invalid_counters_without_leaking_details(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / "private-report.xml"
            secret.write_text('<!DOCTYPE x [<!ENTITY e SYSTEM "https://private.invalid/token">]>'
                              '<testsuite tests="1"/>', encoding="utf-8")
            link = root / "linked.xml"
            try:
                link.symlink_to(secret)
            except OSError:
                self.skipTest("symlinks unavailable")
            large = root / "large.xml"
            large.write_text("x" * 1001, encoding="utf-8")
            negative = root / "negative.xml"
            negative.write_text('<testsuite tests="-1"/>', encoding="utf-8")
            huge = root / "huge.xml"
            huge.write_text(f'<testsuite tests="{summary.MAX_COUNTER + 1}"/>', encoding="utf-8")
            invalid = root / "invalid.xml"
            invalid.write_text('<testsuite tests="https://private.invalid/counter-token"/>',
                               encoding="utf-8")
            nan = root / "nan.xml"
            nan.write_text('<testsuite tests="NaN"/>', encoding="utf-8")
            specs = [f"dtd={secret}", f"link={link}", f"large={large}",
                     f"negative={negative}", f"huge={huge}", f"invalid={invalid}",
                     f"nan={nan}"]
            with mock.patch.object(summary, "MAX_REPORT_BYTES", 1000):
                console, markdown, issues = summary.generate(specs, [], [])
        self.assertEqual(7, issues)
        self.assertNotIn("private.invalid", console + markdown)
        self.assertNotIn(str(root), console + markdown)
        self.assertNotIn("token", console + markdown)

    def test_rejects_duplicate_and_markdown_injecting_labels_and_large_globs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "one.xml"
            report.write_text('<testsuite tests="1"/>', encoding="utf-8")
            specs = [f"safe={report}", f"safe={report}", f"bad|label={report}",
                     f"other={report}"]
            _, markdown, issues = summary.generate(specs, [], [])
            many = [str(root / f"report-{index}.xml")
                    for index in range(summary.MAX_GLOB_MATCHES + 1)]
            with mock.patch.object(summary.glob, "iglob", return_value=iter(many)):
                _, too_many_markdown, too_many_issues = summary.generate(
                    [f"bounded={root / '*.xml'}"], [], [])
        self.assertEqual(3, issues)
        self.assertNotIn("bad|label", markdown)
        self.assertIn("DUPLICATE", markdown)
        self.assertEqual(1, too_many_issues)
        self.assertIn("TOO MANY", too_many_markdown)

    def test_symlinked_output_fails_without_partial_publication_in_both_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.md"
            target.write_text("unchanged", encoding="utf-8")
            output = root / "summary.md"
            step_summary = root / "step-summary.md"
            step_summary.write_text("existing step summary\n", encoding="utf-8")
            try:
                output.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")
            for strict in (False, True):
                with self.subTest(strict=strict):
                    argv = ["generate_summary.py", "--output", str(output)]
                    if strict:
                        argv.append("--strict")
                    with mock.patch.object(sys, "argv", argv), mock.patch.dict(
                            os.environ, {"GITHUB_STEP_SUMMARY": str(step_summary)}, clear=True):
                        self.assertEqual(1, summary.main())
                    self.assertEqual("unchanged", target.read_text(encoding="utf-8"))
                    self.assertTrue(output.is_symlink())
                    self.assertEqual(
                        "existing step summary\n", step_summary.read_text(encoding="utf-8"))
                    self.assertEqual([], list(root.glob(".summary.md.*.tmp")))

    def test_staging_failure_invalidates_stale_output_without_step_append(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.md"
            output.write_text("stale green", encoding="utf-8")
            step_summary = root / "step-summary.md"
            step_summary.write_text("existing\n", encoding="utf-8")
            argv = ["generate_summary.py", "--output", str(output)]
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(
                    os.environ, {"GITHUB_STEP_SUMMARY": str(step_summary)},
                    clear=True), mock.patch.object(
                    summary.tempfile, "mkstemp", side_effect=OSError("full")):
                self.assertEqual(1, summary.main())
            self.assertFalse(output.exists())
            self.assertEqual("existing\n", step_summary.read_text(encoding="utf-8"))
            self.assertTrue((root / ".summary.md.lock").is_file())

    def test_invalid_lock_timeout_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.md"
            output.write_text("owned", encoding="utf-8")
            step_summary = root / "step-summary.md"
            step_summary.write_text("existing\n", encoding="utf-8")
            argv = ["generate_summary.py", "--output", str(output)]
            environment = {
                "GITHUB_STEP_SUMMARY": str(step_summary),
                "OVERTE_SUMMARY_LOCK_TIMEOUT_SECONDS": "invalid",
            }
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(
                    os.environ, environment, clear=True):
                self.assertEqual(2, summary.main())
            self.assertEqual("owned", output.read_text(encoding="utf-8"))
            self.assertEqual("existing\n", step_summary.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_lock_timeout_preserves_owner_outputs(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.md"
            output.write_text("owned", encoding="utf-8")
            step_summary = root / "step-summary.md"
            step_summary.write_text("existing\n", encoding="utf-8")
            lock_path = root / ".summary.md.lock"
            argv = ["generate_summary.py", "--output", str(output)]
            environment = {
                "GITHUB_STEP_SUMMARY": str(step_summary),
                "OVERTE_SUMMARY_LOCK_TIMEOUT_SECONDS": "0.01",
            }
            with lock_path.open("a+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                with mock.patch.object(sys, "argv", argv), mock.patch.dict(
                        os.environ, environment, clear=True):
                    self.assertEqual(1, summary.main())
            self.assertEqual("owned", output.read_text(encoding="utf-8"))
            self.assertEqual("existing\n", step_summary.read_text(encoding="utf-8"))

    def test_step_summary_symlink_is_rejected_without_touching_its_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "summary.md"
            victim = root / "victim.md"
            victim.write_text("private", encoding="utf-8")
            step_summary = root / "step-summary.md"
            try:
                step_summary.symlink_to(victim)
            except OSError:
                self.skipTest("symlinks unavailable")
            argv = ["generate_summary.py", "--output", str(output)]
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(
                    os.environ, {"GITHUB_STEP_SUMMARY": str(step_summary)},
                    clear=True):
                self.assertEqual(1, summary.main())
            self.assertTrue(output.is_file())
            self.assertEqual("private", victim.read_text(encoding="utf-8"))
            self.assertTrue(step_summary.is_symlink())


if __name__ == "__main__":
    unittest.main()
