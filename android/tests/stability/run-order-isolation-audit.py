#!/usr/bin/env python3
"""Fixed-seed order and parallel-isolation audit for device-free suites."""

from __future__ import annotations

import os
from pathlib import Path
import random
import signal
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed


ROOT = Path(__file__).resolve().parents[2]
BASE_CASES = [
    ("deep-links", ["tests/phone-deep-link-test.sh"]),
    ("asset-cache", ["tests/safe-asset-path-test.sh"]),
    ("javascript", ["tests/javascript/run-tests.sh"]),
    ("native", ["tests/native/run-native-tests.sh"]),
    ("js-endurance", ["tests/javascript/run-lifecycle-endurance.sh"]),
    ("native-endurance", ["tests/native/run-endurance-tests.sh"]),
    ("mutations", ["tests/mutation/run-critical-policy-mutations.sh"]),
]


def serial_order(round_index: int) -> list[tuple[str, list[str]]]:
    order = list(BASE_CASES)
    random.Random(0x4F5645525445 + round_index).shuffle(order)
    return order


def case_invocation(case: tuple[str, list[str]], workspace: Path, replica: str):
    name, command = case
    environment = dict(os.environ)
    environment["OVERTE_NATIVE_TEST_BUILD_DIR"] = str(workspace / f"native-{replica}-{name}")
    environment["OVERTE_TEST_REPORT_DIR"] = str(workspace / f"reports-{replica}-{name}")
    actual = list(command)
    if name == "mutations":
        actual += ["--report", str(workspace / f"mutation-{replica}.json")]
    return actual, environment


def run_process(actual: list[str], environment: dict[str, str], timeout: float = 900):
    process = subprocess.Popen(
        actual, cwd=ROOT, env=environment, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_process_group(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            kill_process_group(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        raise RuntimeError(f"timed out after {timeout}s\n{stdout[-8000:]}\n{stderr[-8000:]}")
    return subprocess.CompletedProcess(actual, process.returncode, stdout, stderr)


def kill_process_group(pid: int, requested_signal: signal.Signals) -> bool:
    """Return false when the group won the exit-vs-kill race."""
    try:
        os.killpg(pid, requested_signal)
        return True
    except ProcessLookupError:
        return False


def run_case(case: tuple[str, list[str]], workspace: Path, replica: str) -> tuple[str, int]:
    name, _ = case
    actual, environment = case_invocation(case, workspace, replica)
    result = run_process(actual, environment)
    if result.returncode != 0:
        raise RuntimeError(
            f"{name} ({replica}) failed with {result.returncode}\n"
            f"{result.stdout[-8000:]}\n{result.stderr[-8000:]}")
    return name, result.returncode


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="overte-stability-") as temporary:
        workspace = Path(temporary)
        if os.environ.get("OVERTE_STABILITY_FIXTURE_FAIL") == "1":
            run_case(("intentional-failure", ["python3", "-c", "raise SystemExit(23)"]), workspace, "fixture")
        for round_index in range(2):
            order = serial_order(round_index)
            print("serial order", round_index + 1, ":", ", ".join(name for name, _ in order), flush=True)
            for case in order:
                run_case(case, workspace, f"serial-{round_index}")

        parallel = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            for replica in range(2):
                for case in BASE_CASES:
                    parallel.append(executor.submit(run_case, case, workspace, f"parallel-{replica}"))
            for future in as_completed(parallel):
                future.result()

        # Robolectric owns one Gradle project output tree. Launch two contenders
        # together: the bounded repository flock must serialize them cleanly.
        with ThreadPoolExecutor(max_workers=2) as executor:
            contenders = [executor.submit(
                run_case, ("robolectric", ["tests/robolectric/run-tests.sh"]),
                workspace, f"locked-{index}") for index in range(2)]
            for contender in contenders:
                contender.result()
    print("Stability audit passed: two shuffled serial rounds and two parallel replicas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
