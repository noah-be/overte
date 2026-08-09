#!/usr/bin/env python3
"""Create honest console and Markdown summaries from Android test artifacts."""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_GLOB_MATCHES = 256
MAX_COUNTER = 1_000_000_000
SAFE_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,63}")
JACOCO_DOCTYPE = (b'<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" '
                  b'"report.dtd">')
COBERTURA_DOCTYPE = (b"<!DOCTYPE coverage SYSTEM "
                     b"'http://cobertura.sourceforge.net/xml/coverage-04.dtd'>")


def report_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("report is not a regular file")
    size = path.stat().st_size
    if size > MAX_REPORT_BYTES:
        raise ValueError(f"report exceeds {MAX_REPORT_BYTES} byte limit")
    data = path.read_bytes()
    # JaCoCo emits one fixed external-DTD declaration. ElementTree does not
    # need it for counters, so remove that exact declaration and reject every
    # other DTD/entity construct before parsing.
    data = data.replace(JACOCO_DOCTYPE, b"", 1)
    data = data.replace(COBERTURA_DOCTYPE, b"", 1)
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("XML DTD/entity declarations are forbidden")
    return data


def number(value: str | None, name: str) -> int:
    try:
        result = int(value or "0")
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error
    if result < 0 or result > MAX_COUNTER:
        raise ValueError(f"out-of-range {name}")
    return result


def junit(path: Path) -> dict:
    root = ET.fromstring(report_bytes(path))
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if root.tag == "testsuites" and not suites:
        # Node 22+'s native junit reporter emits testcase elements directly
        # below testsuites rather than adding a synthetic suite wrapper.
        cases = list(root.findall("testcase"))
        if cases:
            totals = {
                "tests": len(cases),
                "failures": sum(case.find("failure") is not None for case in cases),
                "errors": sum(case.find("error") is not None for case in cases),
                "skipped": sum(case.find("skipped") is not None for case in cases),
            }
            totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
            return totals
    if not suites:
        raise ValueError("no testsuite element")
    totals = {key: sum(number(item.get(key), key) for item in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    if totals["passed"] < 0:
        raise ValueError("JUnit counters are inconsistent")
    return totals


def coverage_xml(path: Path) -> dict:
    root = ET.fromstring(report_bytes(path))
    if root.tag == "report":
        counters = {item.get("type"): item for item in root.findall("counter")}
        result = {}
        for key in ("LINE", "BRANCH"):
            item = counters.get(key)
            if item is not None:
                covered, missed = number(item.get("covered"), "covered"), number(item.get("missed"), "missed")
                result[key.lower()] = (covered, covered + missed)
    elif root.tag == "coverage":
        result = {
            "line": (number(root.get("lines-covered"), "lines-covered"),
                     number(root.get("lines-valid"), "lines-valid")),
            "branch": (number(root.get("branches-covered"), "branches-covered"),
                       number(root.get("branches-valid"), "branches-valid")),
        }
    else:
        raise ValueError("unsupported coverage XML root")
    if not result or any(total == 0 or covered > total for covered, total in result.values()):
        raise ValueError("coverage counters are absent or inconsistent")
    return result


def coverage_json(path: Path) -> dict:
    payload = json.loads(report_bytes(path).decode("utf-8"))
    totals = payload.get("total", payload.get("totals", payload))
    result = {}
    for source, target in (("lines", "line"), ("branches", "branch")):
        metric = totals.get(source) if isinstance(totals, dict) else None
        if isinstance(metric, dict) and "covered" in metric and "total" in metric:
            result[target] = (number(str(metric["covered"]), "covered"),
                              number(str(metric["total"]), "total"))
    if not result or any(total == 0 or covered > total for covered, total in result.values()):
        raise ValueError("unsupported or inconsistent coverage JSON")
    return result


def mutation(path: Path) -> dict:
    payload = json.loads(report_bytes(path).decode("utf-8"))
    values = {key: number(str(payload.get(key, 0)), key)
              for key in ("killed", "survived", "errors")}
    mutants = payload.get("mutants")
    values["total"] = len(mutants) if isinstance(mutants, list) else sum(values.values())
    if values["total"] == 0 or sum(values[key] for key in ("killed", "survived", "errors")) != values["total"]:
        raise ValueError("mutation counters are absent or inconsistent")
    mode = str(payload.get("mode", "unknown"))
    values["mode"] = mode if mode in {"quick", "extended"} else "unknown"
    return values


def percent(pair: tuple[int, int]) -> str:
    return f"{100.0 * pair[0] / pair[1]:.2f}% ({pair[0]}/{pair[1]})"


def generate(junit_specs: list[str], coverage_specs: list[str], mutation_specs: list[str]) -> tuple[str, str, int]:
    rows, issues, labels, reports = [], [], set(), set()

    def load_specs(specs, loader, kind, formatter):
        for spec in specs:
            label, separator, pattern = spec.partition("=")
            if not separator or not label or not pattern:
                issues.append(f"invalid {kind} specification")
                continue
            if not SAFE_LABEL.fullmatch(label) or label in labels:
                issues.append(f"invalid or duplicate {kind} label")
                continue
            labels.add(label)
            unique_matches = set()
            for item in glob.iglob(pattern):
                unique_matches.add(Path(item))
                if len(unique_matches) > MAX_GLOB_MATCHES:
                    break
            matches = sorted(unique_matches)
            if not matches:
                issues.append(f"missing {kind} report: {label}")
                rows.append((kind, label, "MISSING"))
                continue
            if len(matches) > MAX_GLOB_MATCHES:
                issues.append(f"too many {kind} reports: {label} (limit {MAX_GLOB_MATCHES})")
                rows.append((kind, label, "TOO MANY"))
                continue
            report_keys = {path.absolute() for path in matches}
            if reports.intersection(report_keys):
                issues.append(f"duplicate {kind} report input: {label}")
                rows.append((kind, label, "DUPLICATE"))
                continue
            reports.update(report_keys)
            aggregate = []
            for path in matches:
                try:
                    aggregate.append(loader(path))
                except (OSError, ValueError, UnicodeError, ET.ParseError,
                        json.JSONDecodeError) as error:
                    # Never emit caller paths, URLs, XML content or test output.
                    if isinstance(error, ET.ParseError):
                        reason = "invalid XML"
                    elif isinstance(error, json.JSONDecodeError):
                        reason = "invalid JSON"
                    elif isinstance(error, UnicodeError):
                        reason = "invalid UTF-8"
                    elif isinstance(error, OSError):
                        reason = "I/O error"
                    else:
                        reason = str(error)
                    issues.append(f"malformed {kind} report: {label}: {reason}")
            if len(aggregate) != len(matches):
                rows.append((kind, label, "MALFORMED"))
            elif kind == "JUnit":
                total = {key: sum(item[key] for item in aggregate)
                         for key in ("tests", "passed", "failures", "errors", "skipped")}
                rows.append((kind, label, formatter(total)))
            elif len(aggregate) == 1:
                rows.append((kind, label, formatter(aggregate[0])))
            else:
                rows.extend((kind, f"{label}/{index}", formatter(item))
                            for index, item in enumerate(aggregate, start=1))

    load_specs(junit_specs, junit, "JUnit", lambda item:
               f"{item['passed']} passed, {item['failures'] + item['errors']} failed, {item['skipped']} skipped / {item['tests']}")

    def load_coverage(path):
        return coverage_json(path) if path.suffix == ".json" else coverage_xml(path)
    load_specs(coverage_specs, load_coverage, "Coverage", lambda item:
               ", ".join(f"{key} {percent(value)}" for key, value in item.items()))
    load_specs(mutation_specs, mutation, "Mutation", lambda item:
               f"{item['killed']}/{item['total']} killed, {item['survived']} survived, {item['errors']} errors ({item['mode']})")

    console = "Android test summary\n" + "\n".join(
        f"- {kind} {label}: {value}" for kind, label, value in rows)
    markdown = "## Android test summary\n\n| Kind | Report | Result |\n|---|---|---|\n" + "".join(
        f"| {kind} | `{label}` | {value} |\n" for kind, label, value in rows)
    if issues:
        console += "\nReport issues:\n" + "\n".join(f"! {issue}" for issue in issues)
        markdown += "\n### Report issues\n\n" + "\n".join(f"- ⚠️ {issue}" for issue in issues) + "\n"
    return console + "\n", markdown, len(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", action="append", default=[], metavar="LABEL=GLOB")
    parser.add_argument("--coverage", action="append", default=[], metavar="LABEL=PATH")
    parser.add_argument("--mutation", action="append", default=[], metavar="LABEL=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true", help="fail when a requested report is missing or malformed")
    args = parser.parse_args()
    console, markdown, issue_count = generate(args.junit, args.coverage, args.mutation)
    print(console, end="")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.is_symlink():
        print("error: summary output cannot be a symlink", file=sys.stderr)
        return 1 if args.strict else 0
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{args.output.name}.", suffix=".tmp", dir=args.output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(markdown)
        os.replace(temporary, args.output)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as destination:
            destination.write(markdown)
    return 1 if args.strict and issue_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
