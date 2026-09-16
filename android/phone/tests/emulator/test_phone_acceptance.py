#!/usr/bin/env python3
"""Focused host tests for the admission-neutral Phone emulator plan."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "emulator" / "phone_acceptance.py"
FIXTURES = Path(__file__).with_name("fixtures")
SPEC = importlib.util.spec_from_file_location("phone_acceptance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
phone_acceptance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = phone_acceptance
SPEC.loader.exec_module(phone_acceptance)


class AcceptancePlanTest(unittest.TestCase):
    def test_checked_in_plan_covers_every_required_capability(self) -> None:
        cases = phone_acceptance.load_plan()
        capabilities = {case.capability for case in cases}
        self.assertTrue(phone_acceptance.REQUIRED_CAPABILITIES.issubset(capabilities))
        self.assertEqual(7, len(cases))

    def test_selectors_are_unique_bounded_android_junit_filters(self) -> None:
        cases = phone_acceptance.load_plan()
        selectors = [case.selector for case in cases]
        self.assertEqual(len(selectors), len(set(selectors)))
        self.assertIn(
            "org.overte.phone.PhoneParityPreparationInstrumentedTest"
            "#unsupportedWebSchemeIsNotExported",
            selectors,
        )
        self.assertTrue(all("\n" not in selector and "\t" not in selector for selector in selectors))

    def test_duplicate_case_fails_closed_without_echoing_private_data(self) -> None:
        original = phone_acceptance.default_plan_path().read_text(encoding="utf-8")
        duplicate = original + original.splitlines(keepends=True)[1]
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "private-plan.tsv"
            plan.write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(phone_acceptance.PlanError, "^acceptance plan contains a duplicate$"):
                phone_acceptance.load_plan(
                    plan_path=plan, repo_root=phone_acceptance.repository_root()
                )

    def test_guard_drift_fails_closed(self) -> None:
        original = phone_acceptance.default_plan_path().read_text(encoding="utf-8")
        changed = original.replace(
            "lib/x86_64/libphoneInterface.so",
            "private-token-that-must-not-be-echoed",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.tsv"
            plan.write_text(changed, encoding="utf-8")
            with self.assertRaisesRegex(
                phone_acceptance.PlanError,
                "^acceptance plan guard no longer matches$",
            ):
                phone_acceptance.load_plan(
                    plan_path=plan, repo_root=phone_acceptance.repository_root()
                )


class AcceptanceResultTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = phone_acceptance.load_plan()

    def test_passing_results_produce_only_fixed_redacted_fields(self) -> None:
        phone_acceptance.verify_results(
            [FIXTURES / "passing-results.xml"], self.cases
        )
        report = phone_acceptance.render_sanitized_report(self.cases)
        self.assertIn("status=POLICY_CASES_VERIFIED_NOT_ACCEPTED\n", report)
        self.assertIn("shared_binding=UNVERIFIED\n", report)
        self.assertIn("case.unsupported_web_deep_link=PASS\n", report)
        self.assertNotIn("private-device", report)
        self.assertNotIn("secret.example", report)

    def test_failure_payload_is_not_reflected_in_error(self) -> None:
        with self.assertRaises(phone_acceptance.ResultError) as caught:
            phone_acceptance.verify_results(
                [FIXTURES / "failed-results.xml"], self.cases
            )
        message = str(caught.exception)
        self.assertEqual(
            "failed acceptance cases: raw_whitespace_deep_link", message
        )
        self.assertNotIn("private-device", message)
        self.assertNotIn("secret.example", message)

    def test_missing_and_duplicate_cases_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            phone_acceptance.ResultError, "^missing acceptance cases:"
        ):
            phone_acceptance.verify_results(
                [FIXTURES / "missing-results.xml"], self.cases
            )
        with self.assertRaisesRegex(
            phone_acceptance.ResultError, "^duplicate acceptance cases:"
        ):
            phone_acceptance.verify_results(
                [FIXTURES / "passing-results.xml", FIXTURES / "passing-results.xml"],
                self.cases,
            )

    def test_result_symlink_and_xml_declarations_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            link = root / "result.xml"
            link.symlink_to(FIXTURES / "passing-results.xml")
            with self.assertRaisesRegex(
                phone_acceptance.ResultError,
                "^instrumentation result is not a regular file$",
            ):
                phone_acceptance.verify_results([link], self.cases)

            declared = root / "declared.xml"
            declared.write_text(
                '<!DOCTYPE testsuite [<!ENTITY private "secret.example">]>'
                '<testsuite/>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                phone_acceptance.ResultError,
                "^instrumentation result contains forbidden XML declarations$",
            ):
                phone_acceptance.verify_results([declared], self.cases)

    def test_report_is_private_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "summary.txt"
            report = phone_acceptance.render_sanitized_report(self.cases)
            phone_acceptance.write_private_report(output, report)
            self.assertEqual(report, output.read_text(encoding="utf-8"))
            self.assertEqual(0o600, os.stat(output).st_mode & 0o777)
            with self.assertRaisesRegex(
                phone_acceptance.ResultError,
                "^sanitized report target already exists$",
            ):
                phone_acceptance.write_private_report(output, report)

    def test_forged_success_counters_and_nonexecuted_cases_are_rejected(self) -> None:
        original = (FIXTURES / "passing-results.xml").read_text(encoding="utf-8")
        variants = [
            original.replace('tests="7"', 'tests="0"'),
            original.replace('failures="0"', 'failures="1"'),
            original.replace('skipped="0"', 'skipped="1"'),
            original.replace('<testcase ', '<testcase status="notrun" ', 1),
            original.replace('<testcase ', '<testcase result="suppressed" ', 1),
            original.replace("<testsuite ", "<arbitrary ").replace("</testsuite>", "</arbitrary>"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.xml"
            for payload in variants:
                with self.subTest(variant=variants.index(payload)):
                    result.write_text(payload, encoding="utf-8")
                    with self.assertRaises(phone_acceptance.ResultError):
                        phone_acceptance.verify_results([result], self.cases)

    def test_unplanned_failure_cannot_be_hidden_by_passing_planned_cases(self) -> None:
        original = (FIXTURES / "passing-results.xml").read_text(encoding="utf-8")
        extra = (
            '<testcase classname="private-input" name="unknown">'
            '<failure message="private-input"/></testcase>'
        )
        payload = original.replace('tests="7"', 'tests="8"').replace(
            'failures="0"', 'failures="1"').replace("</testsuite>", extra + "</testsuite>")
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.xml"
            result.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(phone_acceptance.ResultError,
                                        "^instrumentation suite reports a failure$"):
                phone_acceptance.verify_results([result], self.cases)

    def test_skipped_planned_case_is_not_a_pass(self) -> None:
        original = (FIXTURES / "passing-results.xml").read_text(encoding="utf-8")
        payload = original.replace('skipped="0"', 'skipped="1"').replace(
            'name="rawWhitespaceDeepLinkIsRejected"/>',
            'name="rawWhitespaceDeepLinkIsRejected"><skipped/></testcase>')
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.xml"
            result.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(phone_acceptance.ResultError,
                                        "^failed acceptance cases: raw_whitespace_deep_link$"):
                phone_acceptance.verify_results([result], self.cases)

    def test_matching_names_embedded_in_output_are_not_executed_cases(self) -> None:
        original = (FIXTURES / "passing-results.xml").read_text(encoding="utf-8")
        payload = original.replace('tests="7"', 'tests="0"').replace(
            '<testcase ', '<system-out><testcase ', 1).replace(
            '<system-out>serial=', '</system-out><system-out>serial=')
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.xml"
            result.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(phone_acceptance.ResultError,
                                        "^missing acceptance cases:"):
                phone_acceptance.verify_results([result], self.cases)


if __name__ == "__main__":
    unittest.main()
