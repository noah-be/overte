#!/usr/bin/env python3
"""Run catalogued Android suites and always emit a JUnit XML report."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


ANDROID_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS_ROOT))
from process_control import communicate_with_timeout, popen_session_kwargs  # noqa: E402 -- controlled tests path

DEFAULT_CATALOG = Path(__file__).with_name("catalog.json")
KNOWN_TIERS = {"fast", "host", "prepared-host", "contracts", "android-vr", "regression", "device", "instrumentation", "coverage", "mutation", "mutation-extended", "robolectric", "endurance", "stability"}
MAX_REPORT_OUTPUT_BYTES = 256 * 1024
TERMINATION_GRACE_SECONDS = 1.0
DEFAULT_SUITE_TIMEOUT_SECONDS = 480
DEFAULT_REPORT_LOCK_TIMEOUT_SECONDS = 600.0
DEFAULT_SUITE_TEMP_PARENT = (
    Path("/dev/shm") if Path("/dev/shm").is_dir() and os.access("/dev/shm", os.W_OK)
    else Path(tempfile.gettempdir())
)
SUITE_TEMP_PARENT = Path(os.environ.get("OVERTE_SUITE_TEMP_ROOT", DEFAULT_SUITE_TEMP_PARENT))


def report_lock_timeout() -> float:
    value = os.environ.get(
        "OVERTE_SUITE_REPORT_LOCK_TIMEOUT_SECONDS",
        str(DEFAULT_REPORT_LOCK_TIMEOUT_SECONDS),
    )
    try:
        timeout = float(value)
    except ValueError as error:
        raise ValueError("suite report lock timeout must be a non-negative number") from error
    if timeout < 0 or not timeout < float("inf"):
        raise ValueError("suite report lock timeout must be a non-negative number")
    return timeout


@contextmanager
def report_lifecycle_lock(report: Path, timeout: float):
    """Serialize complete runs publishing the same report without unlink races."""
    report.parent.mkdir(parents=True, exist_ok=True)
    lock_path = report.parent / f".{report.name}.lock"
    with lock_path.open("a+b") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"timed out waiting for suite report lock after {timeout:g} seconds")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def xml_safe(value: object) -> str:
    """Return text accepted by XML 1.0 while preserving useful diagnostics."""
    text = str(value)
    return "".join(character if (character in "\t\n\r" or ord(character) >= 0x20)
                   else "\ufffd" for character in text)


def bounded_report_output(value: object) -> str:
    """Keep reports useful without allowing noisy suites to create huge artifacts."""
    safe = xml_safe(value)
    encoded = safe.encode("utf-8")
    if len(encoded) <= MAX_REPORT_OUTPUT_BYTES:
        return safe
    marker = b"\n... test output truncated by suite runner ...\n"
    available = MAX_REPORT_OUTPUT_BYTES - len(marker)
    head = encoded[:available // 2].decode("utf-8", errors="ignore")
    tail = encoded[-(available - available // 2):].decode("utf-8", errors="ignore")
    return head + marker.decode("ascii") + tail


def run_command(command: list[str], timeout: int, *, cwd: Path = ANDROID_ROOT,
                env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run one suite and guarantee timeout cleanup of its complete POSIX process group."""
    process = subprocess.Popen(
        command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, **popen_session_kwargs(),
    )
    output, _ = communicate_with_timeout(
        process, timeout, termination_grace=TERMINATION_GRACE_SECONDS)
    return subprocess.CompletedProcess(command, process.returncode, output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tier", choices=("fast", "host", "prepared-host", "contracts", "android-vr", "regression",
                                         "device", "instrumentation", "coverage", "mutation", "mutation-extended",
                                         "robolectric", "endurance", "stability", "all"))
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
        timeout = suite.get("timeoutSeconds", DEFAULT_SUITE_TIMEOUT_SECONDS)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"suite {suite_id} has invalid timeoutSeconds")
        optional = suite.get("optionalWhenToolMissing", False)
        if not isinstance(optional, bool):
            raise ValueError(f"suite {suite_id} has invalid optionalWhenToolMissing")
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
            "classname": xml_safe(f"android.{result['kind']}"),
            "name": xml_safe(result["id"]),
            "time": f"{result['duration']:.3f}",
        })
        if result["status"] == "failed":
            failure = ET.SubElement(case, "failure", {"message": f"exit code {result['returncode']}"})
            failure.text = bounded_report_output(result["output"])
        elif result["status"] == "skipped":
            ET.SubElement(case, "skipped", {"message": xml_safe(result["reason"])})
        output = ET.SubElement(case, "system-out")
        output.text = bounded_report_output(result["output"])
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def failure_result(identifier: str, output: str) -> dict:
    return {
        "id": identifier, "kind": "infrastructure", "status": "failed",
        "reason": "", "returncode": 2, "duration": 0.0, "output": output,
    }


def incomplete_result(completed: int, total: int) -> dict:
    return failure_result(
        "suite-run-incomplete",
        f"Suite run incomplete: {completed} of {total} suites completed.\n",
    )


def run_suites(args: argparse.Namespace, report: Path, suites: list[dict]) -> int:
    if not suites:
        output = f"No suites selected for tier {args.tier}\n"
        print(output, end="", file=sys.stderr)
        write_report([failure_result("empty-tier", output)], report, args.tier)
        print(f"JUnit report: {report}", file=sys.stderr)
        return 2

    results = []
    write_report([incomplete_result(0, len(suites))], report, args.tier)
    # Some privacy-sensitive device harnesses deliberately reject report paths
    # inside the source worktree. Keep runner-owned scratch space external.
    suite_temp_parent = SUITE_TEMP_PARENT
    suite_temp_parent.mkdir(parents=True, exist_ok=True)
    for suite in suites:
        print(f"\n[{suite['id']}] {suite['description']}", flush=True)
        started = time.monotonic()
        command = suite["command"]
        try:
            with tempfile.TemporaryDirectory(
                    prefix="overte-android-suite-", dir=suite_temp_parent) as temporary:
                child_env = os.environ.copy()
                child_env["TMPDIR"] = temporary
                completed = run_command(
                    command, suite.get("timeoutSeconds", DEFAULT_SUITE_TIMEOUT_SECONDS),
                    cwd=ANDROID_ROOT, env=child_env)
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
            # Optional wrappers report a specifically diagnosed missing host
            # tool with exit 77. A missing/non-executable wrapper or another
            # spawn failure is suite infrastructure damage, never a skip.
            status, reason, completed = "failed", "", None
        duration = time.monotonic() - started
        returncode = completed.returncode if completed is not None else 127
        print(output, end="")
        results.append({**suite, "status": status, "reason": reason,
                        "returncode": returncode, "duration": duration, "output": output})
        write_report(
            [*results, incomplete_result(len(results), len(suites))], report, args.tier)

    write_report(results, report, args.tier)
    print(f"\nJUnit report: {report}")
    return 1 if any(result["status"] == "failed" for result in results) else 0


def main() -> int:
    args = parse_args()
    report = args.report_dir.resolve() / f"TEST-android-{args.tier}.xml"
    if args.list:
        try:
            suites = load_suites(args.catalog.resolve(), args.tier)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"Unable to load test catalog: {error}", file=sys.stderr)
            return 2
        for suite in suites:
            print(f"{suite['id']}\t{suite['kind']}\t{suite['description']}")
        return 0
    try:
        timeout = report_lock_timeout()
        with report_lifecycle_lock(report, timeout):
            try:
                suites = load_suites(args.catalog.resolve(), args.tier)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                output = f"Unable to load test catalog: {error}\n"
                print(output, end="", file=sys.stderr)
                write_report(
                    [failure_result("catalog-validation", output)], report, args.tier)
                print(f"JUnit report: {report}", file=sys.stderr)
                return 2
            return run_suites(args, report, suites)
    except (TimeoutError, ValueError) as error:
        print(f"Unable to acquire suite report lock: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
