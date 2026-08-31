#!/usr/bin/env python3
"""Hardware-free CI gate for the complete portable device E2E control plane."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


def commands(profile: str) -> list[tuple[str, list[str], bool]]:
    checks = [
        ("policy", [sys.executable, str(ROOT / "validate_policy.py"),
                    "--policy", str(ROOT / "acceptance-policy.json"),
                    "--catalog", str(ROOT / "catalog.json")], False),
        ("contract-versions", [sys.executable, str(ROOT / "validate_contract_versions.py"),
                               "--registry", str(ROOT / "contract-versions.json")], False),
        ("execution-plan", [sys.executable, str(ROOT / "execution_plan.py"),
                            "--policy", str(ROOT / "acceptance-policy.json"),
                            "--catalog", str(ROOT / "catalog.json"),
                            "--profiles", str(ROOT / "execution-profiles.json"),
                            "--platform", "mock", "--suite", "e2e-core",
                            "--fixture-provider", "auto", "--require-ready"], False),
        ("fixtures", [sys.executable, str(ROOT / "fixture/orchestrate.py"), "--check"], False),
    ]
    if profile == "full":
        checks.append((
            "python-self-tests",
            [sys.executable, "-m", "unittest", "discover", "-s",
             "tests/device/self_tests", "-p", "test_*.py"], False))
    else:
        for pattern in (
                "test_common_contracts.py", "test_governance_and_frontier.py",
                "test_execution_plan_pipeline.py", "test_harness.py",
                "test_matrix_evaluator.py"):
            checks.append((
                "python-" + pattern.removeprefix("test_").removesuffix(".py").replace("_", "-"),
                [sys.executable, "-m", "unittest", "discover", "-s",
                 "tests/device/self_tests", "-p", pattern], False))
    checks.append(("qml-contracts", [str(ROOT / "qml/run-qml-tests.sh")], True))
    return checks


def write_junit(path: Path, results: list[dict], elapsed: float) -> None:
    root = ET.Element(
        "testsuite", name="overte-device-control-plane", tests=str(len(results)),
        failures=str(sum(item["status"] == "failed" for item in results)),
        skipped=str(sum(item["status"] == "skipped" for item in results)),
        errors="0", time=f"{elapsed:.3f}")
    for item in results:
        case = ET.SubElement(root, "testcase", classname="overte.device.control-plane",
                             name=item["name"], time=f"{item['durationSeconds']:.3f}")
        if item["status"] == "failed":
            ET.SubElement(case, "failure", message=item["message"]).text = item["output"]
        elif item["status"] == "skipped":
            ET.SubElement(case, "skipped", message=item["message"])
        ET.SubElement(case, "system-out").text = item["output"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    ET.ElementTree(root).write(temporary, encoding="utf-8", xml_declaration=True)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full"), default="quick")
    parser.add_argument("--require-qml", action="store_true")
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 1800:
        parser.error("--timeout-seconds must be from 1 through 1800")
    results = []
    started = time.monotonic()
    for name, command, qml in commands(args.profile):
        item_started = time.monotonic()
        qml_runner = os.environ.get("OVERTE_QML_TEST_RUNNER") or shutil.which(
            "qmltestrunner")
        if qml and not qml_runner:
            status = "failed" if args.require_qml else "skipped"
            output = "qmltestrunner is unavailable\n"
            message = "required QML host tool is unavailable"
        else:
            try:
                result = subprocess.run(
                    command, cwd=REPOSITORY, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, timeout=args.timeout_seconds, check=False)
                status = ("skipped" if result.returncode == 77 and not args.require_qml else
                          "passed" if result.returncode == 0 else "failed")
                output = result.stdout
                message = "" if status == "passed" else f"exit code {result.returncode}"
            except subprocess.TimeoutExpired as error:
                status, message = "failed", f"timeout after {args.timeout_seconds}s"
                output = error.stdout if isinstance(error.stdout, str) else ""
        duration = time.monotonic() - item_started
        print(f"{status.upper():7} {name:<28} {duration:7.3f}s")
        results.append({"name": name, "status": status, "message": message,
                        "output": output, "durationSeconds": duration})
    elapsed = time.monotonic() - started
    if args.junit:
        write_junit(args.junit.resolve(), results, elapsed)
    failed = sum(item["status"] == "failed" for item in results)
    print(f"Device control plane: {len(results) - failed} non-failing, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
