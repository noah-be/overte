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
    Suite("python-test-runner", "quick", (sys.executable, "tests/unittest-runner-test.py")),
    Suite("repository-checks", "quick", (sys.executable, "tests/repository-checks-test.py")),
    Suite("ios-build-qualification", "quick", (sys.executable, "tests/ios-build-qualification-test.py")),
    Suite("repository-policy", "quick", (sys.executable, "tests/repository-policy-test.py")),
    Suite("policy-consistency", "quick", (sys.executable, "tools/repository-policy/check.py")),
    Suite("documentation-contracts", "quick", (sys.executable, "tests/documentation-test.py")),
    Suite("repository-doctor", "quick", (sys.executable, "tests/repository-health-test.py")),
    Suite("repository-maintenance", "quick", (sys.executable, "tests/repository-maintenance-test.py")),
    Suite("branch-policy", "quick", (sys.executable, "tests/branch-policy-test.py")),
    Suite("branch-name-guard", "quick", (sys.executable, "tests/branch-name-guard-test.py")),
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
    Suite("device-control-plane-full", "host", (
        sys.executable, "tests/device/run_control_plane_tests.py", "--profile", "full", "--require-qml",
        "--junit", "build/test-results/device-e2e-control-plane.xml")),
    Suite("documentation", "quick", (
        sys.executable, "tests/check-documentation.py", "--all")),
    Suite("native-smoke", "quick", (
        sys.executable, "tests/device/contracts/world-entry/test_phone_spawn_gate.py")),
    Suite("native-registration", "quick", (sys.executable, "tests/native-registration-test.py")),
    Suite("device-result-schema", "quick", (
        sys.executable, "tests/run-unittest-suite.py", "tests/device/schema")),
    Suite("device-jenkins", "quick", (
        sys.executable, "tests/run-unittest-suite.py", "tests/device/jenkins")),
    Suite("desktop-input-protocol", "quick", (
        sys.executable, "tests/run-unittest-suite.py", "tests/device/adapters/desktop_oculix",
        "--pattern", "test_wayland_libei_client.py")),
    Suite("performance-contracts", "quick", (
        sys.executable, "tests/run-unittest-suite.py", "tests/performance/schema")),
    Suite("server-console-behavior", "quick", (
        "node", "--test", "server-console/test/open-url.test.js", "server-console/test/file-tail.test.js",
        "server-console/test/notification-compat.test.js")),
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
    parser.add_argument("--profile", choices=("quick", "host", "full"), default="quick",
                        help="quick is dependency-light; host includes complete portable contracts; "
                             "full adds a configured native build to quick")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--platform-only", action="store_true",
                        help="run declared product suites when reusing shared parent qualification")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--host-timeout", type=int, default=900,
                        help="total timeout for the complete host control-plane suite (default: 900 seconds)")
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--native-build-dir", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if not 1 <= args.host_timeout <= 1800:
        parser.error("--host-timeout must be from 1 through 1800")
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
    if args.profile == "host":
        # The full control plane includes all quick device checks and the same
        # phone-spawn production regression; do not execute those subsets twice.
        return [suite for suite in SUITES if suite.layer in {"quick", "host"}
                and suite.name not in {"device-e2e-contracts", "native-smoke"}]
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


def stop_process(process: subprocess.Popen) -> str:
    """Let nested schedulers clean their workers before forcing the suite down."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = process.communicate()
    return output


def run_command(command: list[str], timeout: int, cancelled: list[int]) -> tuple[int, str, str]:
    if cancelled:
        return 128 + cancelled[0], "", f"interrupted by signal {cancelled[0]}"
    # Signal handlers only set a flag. Cancellation cannot interrupt Popen before
    # its process is registered here for cleanup, even while the child starts.
    process = subprocess.Popen(command, cwd=ROOT, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancelled:
                return (128 + cancelled[0], stop_process(process),
                        f"interrupted by signal {cancelled[0]}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return 1, stop_process(process), f"timeout after {timeout}s"
            try:
                output, _ = process.communicate(timeout=min(0.1, remaining))
                if cancelled:
                    return (128 + cancelled[0], stop_process(process),
                            f"interrupted by signal {cancelled[0]}")
                return process.returncode, output, ""
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        stop_process(process)
        raise


def run_suites(args: argparse.Namespace, suites: list[Suite], cancelled: list[int]) -> int:

    results = []
    overall_started = time.monotonic()
    for suite in suites:
        command = list(suite.command)
        timeout = args.timeout
        if suite.name == "device-control-plane-full":
            timeout = args.host_timeout
            command.extend(("--timeout-seconds", str(timeout)))
        if suite.name == "native-ctest" and args.native_build_dir:
            command.append(str(args.native_build_dir))
        started = time.monotonic()
        returncode, output, message = run_command(command, timeout, cancelled)
        duration = time.monotonic() - started
        status = "passed" if returncode == 0 else "failed"
        message = message or ("" if returncode == 0 else f"exit code {returncode}")
        print(f"{status.upper():7} {suite.name:<24} {duration:7.3f}s")
        if status == "failed":
            print(output.rstrip(), file=sys.stderr)
        results.append(dict(name=suite.name, status=status, message=message,
                            output=output, time=duration))
        if cancelled or (status == "failed" and args.fail_fast):
            break

    elapsed = time.monotonic() - overall_started
    if args.junit:
        write_junit(args.junit, results, elapsed)
        print(f"JUnit: {args.junit}")
    passed = sum(item["status"] == "passed" for item in results)
    failed = sum(item["status"] == "failed" for item in results)
    print(f"Overte project suite: {passed} passed, {failed} failed ({elapsed:.2f}s)")
    return 128 + cancelled[0] if cancelled else 1 if failed else 0


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
    cancelled = []

    def interrupted(signum, _frame):
        if not cancelled:
            cancelled.append(signum)

    previous = {signum: signal.signal(signum, interrupted)
                for signum in (signal.SIGINT, signal.SIGTERM)}
    try:
        return run_suites(args, suites, cancelled)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
