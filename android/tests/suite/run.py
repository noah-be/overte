#!/usr/bin/env python3
"""Run catalogued Android suites and always emit a JUnit XML report."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


ANDROID_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = Path(__file__).with_name("catalog.json")
KNOWN_TIERS = {"fast", "host", "contracts", "regression", "device", "instrumentation", "coverage", "mutation", "robolectric"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tier", choices=("fast", "host", "contracts", "regression",
                                         "device", "instrumentation", "coverage", "mutation",
                                         "robolectric", "all"))
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--report-dir", type=Path, default=ANDROID_ROOT / "build" / "test-results" / "suite")
    parser.add_argument("--list", action="store_true", help="list selected suites without running them")
    return parser.parse_args()


def load_suites(catalog_path: Path, tier: str) -> list[dict]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("suites"), list):
        raise ValueError("unsupported test catalog schema")
    selected = []
    seen = set()
    for suite in payload["suites"]:
        suite_id = suite.get("id")
        if not isinstance(suite_id, str) or not suite_id or suite_id in seen:
            raise ValueError("suite ids must be unique non-empty strings")
        seen.add(suite_id)
        for field in ("kind", "description"):
            if not isinstance(suite.get(field), str) or not suite[field]:
                raise ValueError(f"suite {suite_id} requires a non-empty {field}")
        command = suite.get("command")
        if (not isinstance(command, list) or not command
                or any(not isinstance(part, str) or not part for part in command)):
            raise ValueError(f"suite {suite_id} requires a non-empty string command list")
        tiers = suite.get("tiers")
        if not isinstance(tiers, list) or not tiers or not set(tiers) <= KNOWN_TIERS:
            raise ValueError(f"suite {suite_id} has invalid tiers")
        if tier == "all" or tier in suite.get("tiers", []):
            selected.append(suite)
    return selected


def write_report(results: list[dict], destination: Path, tier: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    failures = sum(result["status"] == "failed" for result in results)
    skipped = sum(result["status"] == "skipped" for result in results)
    root = ET.Element("testsuite", {
        "name": f"android-{tier}",
        "tests": str(len(results)),
        "failures": str(failures),
        "errors": "0",
        "skipped": str(skipped),
        "time": f"{sum(result['duration'] for result in results):.3f}",
    })
    for result in results:
        case = ET.SubElement(root, "testcase", {
            "classname": f"android.{result['kind']}",
            "name": result["id"],
            "time": f"{result['duration']:.3f}",
        })
        if result["status"] == "failed":
            failure = ET.SubElement(case, "failure", {"message": f"exit code {result['returncode']}"})
            failure.text = result["output"]
        elif result["status"] == "skipped":
            ET.SubElement(case, "skipped", {"message": result["reason"]})
        output = ET.SubElement(case, "system-out")
        output.text = result["output"]
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)


def main() -> int:
    args = parse_args()
    report = args.report_dir.resolve() / f"TEST-android-{args.tier}.xml"
    try:
        suites = load_suites(args.catalog.resolve(), args.tier)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        output = f"Unable to load test catalog: {error}\n"
        print(output, end="", file=sys.stderr)
        write_report([{
            "id": "catalog-validation", "kind": "infrastructure", "status": "failed",
            "reason": "", "returncode": 2, "duration": 0.0, "output": output,
        }], report, args.tier)
        print(f"JUnit report: {report}", file=sys.stderr)
        return 2
    if args.list:
        for suite in suites:
            print(f"{suite['id']}\t{suite['kind']}\t{suite['description']}")
        return 0
    if not suites:
        print(f"No suites selected for tier {args.tier}", file=sys.stderr)
        return 2

    results = []
    for suite in suites:
        print(f"\n[{suite['id']}] {suite['description']}", flush=True)
        started = time.monotonic()
        command = suite["command"]
        try:
            completed = subprocess.run(
                command,
                cwd=ANDROID_ROOT,
                env=os.environ.copy(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=suite.get("timeoutSeconds", 1800),
            )
            output = completed.stdout
            if completed.returncode == 77 and suite.get("optionalWhenToolMissing"):
                status, reason = "skipped", "required optional host tool is unavailable"
            else:
                status = "passed" if completed.returncode == 0 else "failed"
                reason = ""
        except subprocess.TimeoutExpired as error:
            partial_output = error.stdout or ""
            if isinstance(partial_output, bytes):
                partial_output = partial_output.decode("utf-8", errors="replace")
            output = partial_output + f"\nSuite timed out after {error.timeout} seconds.\n"
            status, reason, completed = "failed", "timeout", None
        except OSError as error:
            output = f"{error}\n"
            if suite.get("optionalWhenToolMissing"):
                status, reason, completed = "skipped", str(error), None
            else:
                status, reason, completed = "failed", "", None
        duration = time.monotonic() - started
        returncode = completed.returncode if completed is not None else 127
        print(output, end="")
        results.append({**suite, "status": status, "reason": reason,
                        "returncode": returncode, "duration": duration, "output": output})
        write_report(results, report, args.tier)

    write_report(results, report, args.tier)
    print(f"\nJUnit report: {report}")
    return 1 if any(result["status"] == "failed" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
