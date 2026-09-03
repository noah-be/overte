#!/usr/bin/env python3
"""Layered, hardware-independent Overte project test runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Suite:
    name: str
    layer: str
    command: tuple[str, ...]


SUITES = (
    Suite("project-runner", "quick", (sys.executable, "tests/project-suite-self-test.py")),
    Suite("branch-policy", "quick", (sys.executable, "tests/branch-policy-test.py")),
    Suite("workflow-action-pins", "quick", (sys.executable, "tests/workflow-action-pin-test.py")),
    Suite("desktop-topology", "quick", (sys.executable, "tests/desktop-branch-topology-test.py")),
    Suite("workflow-contracts", "quick", (sys.executable, "tests/workflow-contract-test.py")),
    Suite("repository-health", "quick", (sys.executable, "tests/project-health-test.py")),
    Suite("project-coverage", "quick", (sys.executable, "tests/project-coverage-test.py")),
    Suite("javascript-behavior", "quick", ("node", "tests/mocha/test/testVirtualBaton.js")),
    Suite("device-e2e-contracts", "quick", (
        sys.executable, "tests/device/run_control_plane_tests.py", "--profile", "quick",
        "--junit", "build/test-results/device-e2e-contracts.xml")),
    Suite("documentation", "documentation", (
        sys.executable, "tests/check-documentation.py", "--base", "HEAD^1")),
    Suite("pico4-device-free", "quick", ("bash", "android/vr/pico/tests/pico-device-free-test.sh")),
    Suite("native-ctest", "native", ("bash", "tests/project-native-test.sh")),
)

SUITE_ALIASES = {"device-control-plane": "device-e2e-contracts"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full"), default="quick",
                        help="quick is dependency-light; full also requires a configured native build")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--native-build-dir", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


def select(args: argparse.Namespace) -> list[Suite]:
    requested = set(args.suite)
    known = {suite.name for suite in SUITES}
    unknown = sorted(requested - known - set(SUITE_ALIASES))
    if unknown:
        raise ValueError("unknown suites: " + ", ".join(unknown))
    names = {SUITE_ALIASES.get(name, name) for name in requested}
    if names:
        return [suite for suite in SUITES if suite.name in names]
    layers = {"quick"} if args.profile == "quick" else {"quick", "native"}
    return [suite for suite in SUITES if suite.layer in layers]


def write_junit(path: Path, results: list[dict[str, object]], elapsed: float) -> None:
    failures = sum(item["status"] == "failed" for item in results)
    root = ET.Element("testsuite", name="overte-project", tests=str(len(results)),
                      failures=str(failures), skipped="0", time=f"{elapsed:.3f}")
    for item in results:
        case = ET.SubElement(root, "testcase", name=str(item["name"]),
                             classname="overte.project", time=f"{item['time']:.3f}")
        if item["status"] == "failed":
            failure = ET.SubElement(case, "failure", message=str(item["message"]))
            failure.text = str(item["output"])
        ET.SubElement(case, "system-out").text = str(item["output"])
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    args = arguments()
    try:
        suites = select(args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.list:
        for suite in suites:
            print(f"{suite.name:<24} {suite.layer}")
        return 0

    results = []
    overall_started = time.monotonic()
    for suite in suites:
        command = list(suite.command)
        if suite.name == "native-ctest" and args.native_build_dir:
            command.append(str(args.native_build_dir))
        started = time.monotonic()
        process = subprocess.Popen(command, cwd=ROOT, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            output, _ = process.communicate(timeout=args.timeout)
            duration = time.monotonic() - started
            status = "passed" if process.returncode == 0 else "failed"
            message = "" if process.returncode == 0 else f"exit code {process.returncode}"
        except subprocess.TimeoutExpired as error:
            os.killpg(process.pid, signal.SIGKILL)
            remaining, _ = process.communicate()
            duration = time.monotonic() - started
            status, message = "failed", f"timeout after {args.timeout}s"
            prefix = error.stdout if isinstance(error.stdout, str) else ""
            output = prefix + remaining
        print(f"{status.upper():7} {suite.name:<24} {duration:7.3f}s")
        if status == "failed":
            print(output.rstrip(), file=sys.stderr)
        results.append(dict(name=suite.name, status=status, message=message,
                            output=output, time=duration))
        if status == "failed" and args.fail_fast:
            break

    elapsed = time.monotonic() - overall_started
    if args.junit:
        write_junit(args.junit, results, elapsed)
        print(f"JUnit: {args.junit}")
    passed = sum(item["status"] == "passed" for item in results)
    failed = sum(item["status"] == "failed" for item in results)
    print(f"Overte project suite: {passed} passed, {failed} failed ({elapsed:.2f}s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
