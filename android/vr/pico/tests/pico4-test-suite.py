#!/usr/bin/env python3
"""Hardware-independent Pico 4 regression-suite orchestrator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


TEST_DIR = Path(__file__).resolve().parent
ANDROID_DIR = TEST_DIR.parent


@dataclass(frozen=True)
class Test:
    name: str
    category: str
    command: tuple[str, ...]
    requires: tuple[str, ...] = ()


def test(name: str, category: str, *command: str, requires: tuple[str, ...] = ()) -> Test:
    return Test(name, category, command, requires)


PYTHON = sys.executable
TESTS = (
    test("suite-runner", "infrastructure", PYTHON, "pico4-test-suite-self-test.py"),
    test("coverage-matrix", "infrastructure", PYTHON, "pico4-coverage-test.py"),
    test("shell-syntax", "infrastructure", "bash", "pico-shell-syntax-test.sh"),
    test("package-contract", "android", PYTHON, "pico-package-contract-test.py"),
    test("apk-verifier", "android", PYTHON, "pico-apk-verifier-test.py"),
    test("release-contract", "android", PYTHON, "pico-release-contract-test.py"),
    test("platform-glue", "android", PYTHON, "pico-platform-glue-test.py"),
    test("android-entrypoints", "android", PYTHON, "pico-android-entrypoints-test.py"),
    test("webview-bridge", "webview", PYTHON, "pico-webview-bridge-test.py"),
    test("webview-touch-state", "webview", "bash", "pico-webview-input-test.sh", requires=("javac", "java")),
    test("audio-capture-state", "audio", "bash", "pico-audio-capture-state-test.sh", requires=("javac", "java")),
    test("audio-native-transport", "audio", PYTHON, "pico-audio-transport-test.py"),
    test("openxr-loader", "openxr", PYTHON, "pico-openxr-loader-test.py"),
    test("openxr-input", "openxr", PYTHON, "pico-openxr-input-test.py"),
    test("openxr-display", "openxr", PYTHON, "pico-openxr-display-test.py"),
    test("interaction-diagnostics", "interaction", "node", "pico-interaction-diagnostics-test.js", requires=("node",)),
    test("tablet-lifecycle", "interaction", "node", "pico-tablet-lifecycle-test.js", requires=("node",)),
    test("tablet-settings", "interaction", "node", "pico-tablet-settings-test.js", requires=("node",)),
    test("tablet-e2e-adapter", "interaction", PYTHON, "pico-tablet-e2e-adapter-test.py"),
    test("create-qml", "interaction", PYTHON, "pico-create-qml-test.py"),
    test("create-properties", "interaction", "node", "pico-create-properties-validation-test.js", requires=("node",)),
    test("create-message", "interaction", "node", "pico-create-message-validation-test.js", requires=("node",)),
    test("avatar-hotpath", "performance", PYTHON, "pico-avatar-hotpath-test.py"),
    test("shadergen-jobs", "performance", PYTHON, "pico-shadergen-jobs-test.py"),
    test("world-state", "world", PYTHON, "pico-world-state-test.py"),
    test("microphone-runner", "tooling", "bash", "pico-microphone-test-test.sh"),
    test("unattended-runner", "tooling", "bash", "pico-unattended-test-test.sh"),
    test("device-lock", "tooling", "bash", "pico-device-lock-test.sh"),
    test("device-acceptance", "tooling", "bash", "pico-device-acceptance-test.sh"),
    test("serverless-fixtures", "world", "bash", "serverless-hub-fixture-test.sh", requires=("jq",)),
    test("power-analyzer", "performance", PYTHON, "test_analyze_pico4_power.py"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list tests without running them")
    parser.add_argument("--category", action="append", default=[], help="run a category (repeatable)")
    parser.add_argument("--test", action="append", default=[], help="run a named test (repeatable)")
    parser.add_argument("--timeout", type=int, default=120, help="seconds allowed per test (default: 120)")
    parser.add_argument("--junit", type=Path, help="write a JUnit XML report")
    parser.add_argument("--fail-fast", action="store_true", help="stop after the first failure")
    parser.add_argument("--skip-missing", action="store_true", help="report missing optional tools as skipped")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


def selected_tests(args: argparse.Namespace) -> list[Test]:
    names = set(args.test)
    categories = set(args.category)
    known_names = {item.name for item in TESTS}
    known_categories = {item.category for item in TESTS}
    unknown = sorted(names - known_names)
    unknown_categories = sorted(categories - known_categories)
    if unknown or unknown_categories:
        details = []
        if unknown:
            details.append("unknown tests: " + ", ".join(unknown))
        if unknown_categories:
            details.append("unknown categories: " + ", ".join(unknown_categories))
        raise ValueError("; ".join(details))
    if not names and not categories:
        return list(TESTS)
    return [item for item in TESTS if item.name in names or item.category in categories]


def junit_report(path: Path, results: list[dict[str, object]], elapsed: float) -> None:
    failures = sum(result["status"] == "failed" for result in results)
    skipped = sum(result["status"] == "skipped" for result in results)
    suite = ET.Element("testsuite", name="pico4-device-free", tests=str(len(results)),
                       failures=str(failures), skipped=str(skipped), time=f"{elapsed:.3f}")
    for result in results:
        case = ET.SubElement(suite, "testcase", name=str(result["name"]),
                             classname=f"pico4.{result['category']}", time=f"{result['time']:.3f}")
        if result["status"] == "failed":
            node = ET.SubElement(case, "failure", message=str(result["message"]))
            node.text = str(result["output"])
        elif result["status"] == "skipped":
            ET.SubElement(case, "skipped", message=str(result["message"]))
        output = str(result["output"])
        if output:
            ET.SubElement(case, "system-out").text = output
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    args = parse_args()
    try:
        chosen = selected_tests(args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.list:
        for item in chosen:
            print(f"{item.name:<26} {item.category}")
        return 0

    results: list[dict[str, object]] = []
    started = time.monotonic()
    for item in chosen:
        missing = [tool for tool in item.requires if shutil.which(tool) is None]
        if missing:
            message = "missing tools: " + ", ".join(missing)
            status = "skipped" if args.skip_missing else "failed"
            print(f"{status.upper():7} {item.name} ({message})")
            results.append(dict(name=item.name, category=item.category, status=status,
                                message=message, output="", time=0.0))
            if status == "failed" and args.fail_fast:
                break
            continue
        command = list(item.command)
        if len(command) > 1 and not os.path.isabs(command[1]):
            command[1] = str(TEST_DIR / command[1])
        test_started = time.monotonic()
        try:
            completed = subprocess.run(command, cwd=TEST_DIR, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       timeout=args.timeout, check=False)
            duration = time.monotonic() - test_started
            output = completed.stdout
            status = "passed" if completed.returncode == 0 else "failed"
            message = "" if completed.returncode == 0 else f"exit code {completed.returncode}"
        except subprocess.TimeoutExpired as error:
            duration = time.monotonic() - test_started
            output = (error.stdout or "") if isinstance(error.stdout, str) else ""
            status, message = "failed", f"timeout after {args.timeout}s"
        print(f"{status.upper():7} {item.name:<26} {duration:7.3f}s")
        if status == "failed" and output:
            print(output.rstrip(), file=sys.stderr)
        results.append(dict(name=item.name, category=item.category, status=status,
                            message=message, output=output, time=duration))
        if status == "failed" and args.fail_fast:
            break

    elapsed = time.monotonic() - started
    if args.junit:
        junit_report(args.junit, results, elapsed)
        print(f"JUnit: {args.junit}")
    passed = sum(result["status"] == "passed" for result in results)
    failed = sum(result["status"] == "failed" for result in results)
    skipped = sum(result["status"] == "skipped" for result in results)
    print(f"Pico 4 device-free suite: {passed} passed, {failed} failed, {skipped} skipped ({elapsed:.2f}s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
