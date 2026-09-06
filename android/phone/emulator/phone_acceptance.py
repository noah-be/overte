#!/usr/bin/env python3
"""Fail-closed local preparation for the Android Phone emulator acceptance run."""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence


PLAN_HEADER = (
    "case_id",
    "capability",
    "test_class",
    "test_method",
    "guard_path",
    "guard_token",
)
REQUIRED_CAPABILITIES = frozenset(
    {"packaging", "launch", "deep_link_rejection", "permission_denial", "tablet", "ime"}
)
MAX_PLAN_BYTES = 64 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_RESULT_FILES = 32
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
JAVA_CLASS = re.compile(r"org\.overte\.phone\.[A-Za-z_$][A-Za-z0-9_.$]*\Z")
JAVA_METHOD = re.compile(r"[a-z][A-Za-z0-9_]*\Z")


class PlanError(ValueError):
    """A safe, non-path-bearing validation error."""


class ResultError(ValueError):
    """A safe result error that contains only fixed plan identifiers."""


@dataclass(frozen=True)
class AcceptanceCase:
    case_id: str
    capability: str
    test_class: str
    test_method: str
    guard_path: str
    guard_token: str

    @property
    def selector(self) -> str:
        return f"{self.test_class}#{self.test_method}"


def repository_root() -> Path:
    # android/phone/emulator/phone_acceptance.py -> repository root
    return Path(__file__).resolve(strict=True).parents[3]


def default_plan_path() -> Path:
    return Path(__file__).with_name("acceptance-plan.tsv")


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and ".." not in path.parts
        and path.parts[:2] == ("android", "phone")
    )


def load_plan(
    plan_path: Path | None = None, repo_root: Path | None = None
) -> tuple[AcceptanceCase, ...]:
    plan = plan_path if plan_path is not None else default_plan_path()
    root = repo_root if repo_root is not None else repository_root()
    try:
        if plan.is_symlink() or not plan.is_file():
            raise PlanError("acceptance plan is not a regular file")
        payload = plan.read_bytes()
    except OSError as error:
        raise PlanError("acceptance plan is unreadable") from error
    if not payload or len(payload) > MAX_PLAN_BYTES or b"\0" in payload:
        raise PlanError("acceptance plan has an invalid size or encoding")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PlanError("acceptance plan has an invalid size or encoding") from error

    try:
        rows = list(csv.reader(io.StringIO(text), delimiter="\t", strict=True))
    except csv.Error as error:
        raise PlanError("acceptance plan rows are malformed") from error
    if not rows or tuple(rows[0]) != PLAN_HEADER:
        raise PlanError("acceptance plan header is invalid")

    result: list[AcceptanceCase] = []
    case_ids: set[str] = set()
    selectors: set[str] = set()
    for fields in rows[1:]:
        if len(fields) != len(PLAN_HEADER) or any(not field for field in fields):
            raise PlanError("acceptance plan row is invalid")
        case = AcceptanceCase(*fields)
        if (
            not IDENTIFIER.fullmatch(case.case_id)
            or not IDENTIFIER.fullmatch(case.capability)
            or not JAVA_CLASS.fullmatch(case.test_class)
            or not JAVA_METHOD.fullmatch(case.test_method)
            or not _safe_relative_path(case.guard_path)
            or any(character in case.guard_token for character in "\r\n\t")
        ):
            raise PlanError("acceptance plan row is invalid")
        if case.case_id in case_ids or case.selector in selectors:
            raise PlanError("acceptance plan contains a duplicate")

        guard = root / case.guard_path
        try:
            if guard.is_symlink() or not guard.is_file():
                raise PlanError("acceptance plan guard is unavailable")
            guard_text = guard.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise PlanError("acceptance plan guard is unavailable") from error
        if case.guard_token not in guard_text:
            raise PlanError("acceptance plan guard no longer matches")

        case_ids.add(case.case_id)
        selectors.add(case.selector)
        result.append(case)

    capabilities = {case.capability for case in result}
    if not result or not REQUIRED_CAPABILITIES.issubset(capabilities):
        raise PlanError("acceptance plan omits a required capability")
    return tuple(result)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def verify_results(
    result_paths: Sequence[Path], cases: Sequence[AcceptanceCase]
) -> None:
    if not result_paths or len(result_paths) > MAX_RESULT_FILES:
        raise ResultError("instrumentation result count is invalid")

    planned = {case.selector: case.case_id for case in cases}
    observed: dict[str, list[str]] = {case.case_id: [] for case in cases}
    suite_failed = False
    for result_path in result_paths:
        try:
            if result_path.is_symlink() or not result_path.is_file():
                raise ResultError("instrumentation result is not a regular file")
            with result_path.open("rb") as stream:
                payload = stream.read(MAX_RESULT_BYTES + 1)
        except OSError as error:
            raise ResultError("instrumentation result is unreadable") from error
        if not payload or len(payload) > MAX_RESULT_BYTES or b"\0" in payload:
            raise ResultError("instrumentation result has an invalid size or encoding")
        lowered = payload.lower()
        if b"<!doctype" in lowered or b"<!entity" in lowered:
            raise ResultError("instrumentation result contains forbidden XML declarations")
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as error:
            raise ResultError("instrumentation result is malformed") from error
        if root.tag not in {"testsuite", "testsuites"}:
            raise ResultError("instrumentation result root is invalid")
        suites = [root] if root.tag == "testsuite" else list(root)
        if not suites or any(suite.tag != "testsuite" for suite in suites):
            raise ResultError("instrumentation result suites are invalid")
        for suite in suites:
            # Accept only flat AndroidJUnit suites. Do not fish matching test
            # names out of arbitrary nested output or ignored XML wrappers.
            children = list(suite)
            if any(child.tag not in {"testcase", "properties", "system-out", "system-err"}
                   for child in children):
                raise ResultError("instrumentation result suite structure is invalid")
            testcases = [child for child in children if child.tag == "testcase"]
            counters = {}
            for attribute in ("tests", "failures", "errors", "skipped"):
                value = suite.get(attribute)
                if value is None or not re.fullmatch(r"[0-9]{1,8}", value):
                    raise ResultError("instrumentation result counters are invalid")
                counters[attribute] = int(value)
            actual = {"tests": len(testcases), "failures": 0, "errors": 0, "skipped": 0}
            for testcase in testcases:
                outcomes = [child.tag for child in testcase
                            if child.tag in {"failure", "error", "skipped"}]
                if len(outcomes) > 1:
                    raise ResultError("instrumentation testcase outcome is ambiguous")
                if outcomes:
                    actual[{"failure": "failures", "error": "errors",
                            "skipped": "skipped"}[outcomes[0]]] += 1
                if testcase.get("status", "run") != "run":
                    raise ResultError("instrumentation testcase did not run")
                if testcase.get("result", "completed") != "completed":
                    raise ResultError("instrumentation testcase did not complete")
            if actual != counters:
                raise ResultError("instrumentation result counters disagree with cases")

        for element in (case for suite in suites for case in suite.findall("testcase")):
            test_class = element.attrib.get("classname", "")
            test_method = element.attrib.get("name", "")
            selector = f"{test_class}#{test_method}"
            outcome = "PASS"
            child_names = {_local_name(child.tag) for child in element}
            if "failure" in child_names or "error" in child_names:
                outcome = "FAIL"
                suite_failed = True
            elif "skipped" in child_names:
                outcome = "SKIP"
            case_id = planned.get(selector)
            if case_id is None:
                continue
            observed[case_id].append(outcome)

    missing = [case.case_id for case in cases if not observed[case.case_id]]
    duplicates = [case.case_id for case in cases if len(observed[case.case_id]) > 1]
    failed = [
        case.case_id
        for case in cases
        if observed[case.case_id] and observed[case.case_id][0] != "PASS"
    ]
    if missing:
        raise ResultError("missing acceptance cases: " + ",".join(missing))
    if duplicates:
        raise ResultError("duplicate acceptance cases: " + ",".join(duplicates))
    if failed:
        raise ResultError("failed acceptance cases: " + ",".join(failed))
    if suite_failed:
        raise ResultError("instrumentation suite reports a failure")


def render_sanitized_report(cases: Sequence[AcceptanceCase], shared_bound: bool = False) -> str:
    lines = [
        "format=overte-phone-local-emulator-summary-v1",
        "status=POLICY_CASES_VERIFIED_NOT_ACCEPTED",
        "scope=phone-local-verification",
        "shared_binding=" + ("RESULT_BOUND_NOT_NODE_ACCEPTED" if shared_bound else "UNVERIFIED"),
        "instrumentation_identity=UNVERIFIED",
        "architecture=x86_64",
        "hardware_claim=none",
        f"cases_total={len(cases)}",
    ]
    lines.extend(f"case.{case.case_id}=PASS" for case in cases)
    return "\n".join(lines) + "\n"


def write_private_report(output_path: Path, report: str) -> None:
    try:
        if output_path.is_symlink() or output_path.exists():
            raise ResultError("sanitized report target already exists")
        if not output_path.parent.is_dir() or output_path.parent.is_symlink():
            raise ResultError("sanitized report parent is invalid")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(output_path, flags, 0o600)
        try:
            payload = report.encode("utf-8")
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
    except ResultError:
        raise
    except OSError as error:
        raise ResultError("sanitized report could not be written") from error


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "PHONE_EMULATOR_ARGUMENTS_REJECTED\n")


def build_parser() -> argparse.ArgumentParser:
    parser = PrivateParser(
        description="Validate the local Android Phone emulator acceptance plan."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-plan", help="validate the guarded local plan")
    commands.add_parser("selectors", help="emit bounded AndroidJUnit selectors")
    verify = commands.add_parser(
        "verify-results", help="verify AndroidJUnit XML and write a redacted summary"
    )
    verify.add_argument("--result", action="append", required=True, type=Path)
    verify.add_argument("--output", required=True, type=Path)
    verify.add_argument("--runner-result-root", required=True, type=Path)
    verify.add_argument("--expected-source-sha", required=True)
    verify.add_argument("--expected-artifact-sha256", required=True)
    verify.add_argument("--expected-adapter", required=True,
                        choices=("android-phone-adb", "appium-android"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = load_plan()
        if args.command == "verify-results":
            verify_results(args.result, cases)
            # Consume the original SH-004 verifier through the Phone milestone
            # adapter. Passing policy/JUnit fixtures alone is never acceptance.
            sys.path.insert(0, str(repository_root() / "android/phone/tests/device"))
            from result_adapter import verify_phone_results
            try:
                verify_phone_results(args.runner_result_root, args.expected_source_sha,
                                     args.expected_artifact_sha256,
                                     args.expected_adapter, "emulator")
            except (ValueError, OSError, TypeError, KeyError, RecursionError) as error:
                raise ResultError("shared runner results rejected") from error
            write_private_report(args.output, render_sanitized_report(cases, shared_bound=True))
            print("PHONE_EMULATOR_RESULTS_BOUND_NOT_ACCEPTED")
            return 0
    except (PlanError, ResultError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.command == "selectors":
        for case in cases:
            print(case.selector)
    else:
        print(
            "Android Phone emulator acceptance plan: "
            f"PASS ({len(cases)} cases, {len({case.capability for case in cases})} capabilities)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
