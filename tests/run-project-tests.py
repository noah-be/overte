#!/usr/bin/env python3
"""Layered, hardware-independent Overte project test runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
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
    Suite("dependency-releases", "quick", (sys.executable, "tools/dependency-releases/test.py")),
    Suite("project-runner", "quick", (sys.executable, "tests/project-suite-self-test.py")),
    Suite("repository-checks", "quick", (sys.executable, "tests/repository-checks-test.py")),
    Suite("repository-policy", "quick", (sys.executable, "tests/repository-policy-test.py")),
    Suite("policy-consistency", "quick", (sys.executable, "tools/repository-policy/check.py")),
    Suite("documentation-contracts", "quick", (sys.executable, "tests/documentation-test.py")),
    Suite("repository-doctor", "quick", (sys.executable, "tests/repository-health-test.py")),
    Suite("repository-maintenance", "quick", (sys.executable, "tests/repository-maintenance-test.py")),
    Suite("branch-policy", "quick", (sys.executable, "tests/branch-policy-test.py")),
    Suite("branch-cleanup", "quick", (sys.executable, "tests/branch-cleanup-test.py")),
    Suite("sync-test-reuse", "quick", (sys.executable, "tools/sync-test-reuse/test.py")),
    Suite("workflow-action-pins", "quick", (sys.executable, "tests/workflow-action-pin-test.py")),
    Suite("release-bundle", "quick", (sys.executable, "tools/release/tests/release-bundle-test.py")),
    Suite("workflow-contracts", "quick", (sys.executable, "tests/workflow-contract-test.py")),
    Suite("repository-health", "quick", (sys.executable, "tests/project-health-test.py")),
    Suite("issue-intake", "quick", (sys.executable, "tests/issue-intake-test.py")),
    Suite("project-coverage", "quick", (sys.executable, "tests/project-coverage-test.py")),
    Suite("codeql-remediation", "quick", ("node", "--test", "tests/codeql-remediation-test.js")),
    Suite("javascript-behavior", "quick", ("node", "tests/mocha/test/testVirtualBaton.js")),
    Suite("device-e2e-contracts", "quick", (
        sys.executable, "tests/device/run_control_plane_tests.py", "--profile", "quick",
        "--junit", "build/test-results/device-e2e-contracts.xml")),
    Suite("documentation", "quick", (
        sys.executable, "tests/check-documentation.py", "--all")),
    Suite("native-smoke", "quick", (
        sys.executable, "tests/device/contracts/world-entry/test_phone_spawn_gate.py")),
    Suite("source-layout", "quick", (sys.executable, "tests/source-layout-test.py")),
    Suite("shared-script-behavior", "quick", ("node", "--test", *tuple(
        str(path.relative_to(ROOT)) for path in sorted((ROOT / "tests/javascript/test").glob("*.test.js"))))),
    Suite("native-ctest", "native", ("bash", "tests/project-native-test.sh")),
)

def platform_suites() -> tuple[Suite, ...]:
    """Load explicit branch-owned suites; malformed or missing entries fail closed."""
    profile = json.loads((ROOT / "tests/platform-profile.json").read_text(encoding="utf-8"))
    if set(profile) != {"schema", "platform", "suites"} or profile["schema"] != 1:
        raise ValueError("invalid platform test profile")
    if profile["platform"] not in {"shared", "android"} or not isinstance(profile["suites"], list):
        raise ValueError("invalid platform test profile")
    if profile["platform"] == "shared" and profile["suites"]:
        raise ValueError("shared profile cannot own product suites")
    if profile["platform"] == "android" and not profile["suites"]:
        raise ValueError("Android profile must retain its product suites")
    names = {suite.name for suite in SUITES}
    suites = []
    for entry in profile["suites"]:
        if set(entry) != {"name", "entrypoint", "interpreter"}:
            raise ValueError("invalid platform suite")
        name, path, interpreter = entry["name"], entry["entrypoint"], entry["interpreter"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("duplicate or invalid platform suite name")
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or not (ROOT / relative).is_file():
            raise ValueError("missing or unsafe platform suite entrypoint")
        if not (ROOT / relative).resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("platform suite escapes checkout")
        if interpreter not in {"python", "bash"}:
            raise ValueError("invalid platform suite interpreter")
        names.add(name)
        suites.append(Suite(name, "quick", (sys.executable if interpreter == "python" else "bash", path)))
    return tuple(suites)


PLATFORM_SUITES = platform_suites()
SUITES += PLATFORM_SUITES

SUITE_ALIASES = {"device-control-plane": "device-e2e-contracts"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full"), default="quick",
                        help="quick is dependency-light; full also requires a configured native build")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--platform-only", action="store_true",
                        help="run declared product suites when reusing shared parent qualification")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--native-build-dir", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.platform_only and args.suite:
        parser.error("--platform-only cannot be combined with --suite")
    return args


def select(args: argparse.Namespace) -> list[Suite]:
    if args.platform_only:
        return list(PLATFORM_SUITES)
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
