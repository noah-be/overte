#!/usr/bin/env python3
"""Hardware-free CI gate for the complete portable device E2E control plane."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


def commands(profile: str, self_test_jobs: int | None = None) -> list[tuple[str, list[str], bool]]:
    if self_test_jobs is None:
        self_test_jobs = 2 if sys.platform == "linux" else 1
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
        # Isolated validation dependencies are pinned in tests/requirements-host.txt.
        # These tests also exercise their CLIs inside Linux network namespaces.
        checks.append((
            "artifact-identity",
            [sys.executable, "tests/run-unittest-suite.py",
             "tests/device/schema/artifact-identity"], False))
        checks.append((
            "python-self-tests",
            [sys.executable, "tests/run-unittest-suite.py", "tests/device/self_tests",
             "--jobs", str(self_test_jobs)], False))
        # These production C++ regressions require only the host compiler;
        # Qt-dependent lifecycle harnesses need separate prepared-host validation.
        for name, path in (
            ("phone-voice-buffer", "audio/test_phone_voice_buffer.py"),
            ("phone-spawn-gate", "world-entry/test_phone_spawn_gate.py"),
            ("remote-avatar-keyframes", "world-entry/test_remote_avatar_keyframes.py"),
        ):
            checks.append((name, [sys.executable, str(ROOT / "contracts" / path)], False))
        # Portable production regressions require Qt6 Core/Concurrent/Gui development
        # packages and a host C++ compiler; no device or native client build.
        for path in (
            "audio/test_injector_buffer_publication.py",
            "audio/test_injector_event_delivery.py",
            "audio/test_injector_preparation_lifetime.py",
            "audio/test_recording_safety.py",
            "audio/test_sample_sound_controls.py",
            "dependency/test_cache.py",
            "lifecycle/test_domain_list_history.py",
            "lifecycle/test_domain_list_receiver.py",
            "lifecycle/test_v8_wrapper_teardown.py",
            "graphics/entity-change-thread-test.py",
            "graphics/image-decode-budget-test.py",
            "graphics/image-decode-qt-codec-test.py",
            "graphics/draw-info-object-index-test.py",
        ):
            checks.append((Path(path).stem, [sys.executable, str(ROOT / "contracts" / path)], False))
    else:
        patterns = [
            "test_common_contracts.py", "test_governance_and_frontier.py",
            "test_execution_plan_pipeline.py", "test_harness.py",
            "test_matrix_evaluator.py",
        ]
        stability = ROOT / "self_tests/test_stability_campaign.py"
        if stability.is_file():
            patterns.append(stability.name)
        for pattern in patterns:
            checks.append((
                "python-" + pattern.removeprefix("test_").removesuffix(".py").replace("_", "-"),
                [sys.executable, "tests/run-unittest-suite.py",
                 "tests/device/self_tests", "--pattern", pattern], False))
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


def stop_process(process: subprocess.Popen) -> str:
    # This budget is shorter than the project runner's five-second grace. The
    # unittest scheduler needs at most 2.6 seconds to reap eight worker trees.
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        pass
    try:
        output, _ = process.communicate(timeout=3.5)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        output, _ = process.communicate()
    return output


def run_command(command: list[str], timeout: int, cancelled: list[int]) -> tuple[int, str, str]:
    if cancelled:
        return 128 + cancelled[0], "", f"interrupted by signal {cancelled[0]}"
    # Record the process before reacting to cancellation. A signal during Popen
    # must not strand a scheduler whose workers own separate process groups.
    process = subprocess.Popen(command, cwd=REPOSITORY, text=True,
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


def run_checks(args: argparse.Namespace, cancelled: list[int]) -> int:
    results = []
    started = time.monotonic()
    for name, command, qml in commands(args.profile, args.self_test_jobs):
        if name == "python-self-tests":
            command.extend(("--timeout-seconds", str(args.timeout_seconds)))
            if args.self_test_jobs > 1:
                command.extend(("--report-json", "build/test-results/device-self-tests.json"))
        item_started = time.monotonic()
        qml_runner = os.environ.get("OVERTE_QML_TEST_RUNNER") or shutil.which(
            "qmltestrunner")
        if qml and not qml_runner:
            status = "failed" if args.require_qml else "skipped"
            output = "qmltestrunner is unavailable\n"
            message = "required QML host tool is unavailable"
        else:
            returncode, output, message = run_command(command, args.timeout_seconds, cancelled)
            status = ("skipped" if returncode == 77 and not args.require_qml else
                      "passed" if returncode == 0 else "failed")
            message = message or ("" if status == "passed" else f"exit code {returncode}")
        duration = time.monotonic() - item_started
        print(f"{status.upper():7} {name:<28} {duration:7.3f}s")
        results.append({"name": name, "status": status, "message": message,
                        "output": output, "durationSeconds": duration})
        if cancelled:
            break
    elapsed = time.monotonic() - started
    if args.junit:
        write_junit(args.junit.resolve(), results, elapsed)
    failed = sum(item["status"] == "failed" for item in results)
    print(f"Device control plane: {len(results) - failed} non-failing, {failed} failed")
    return 128 + cancelled[0] if cancelled else 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full"), default="quick")
    parser.add_argument("--require-qml", action="store_true")
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--self-test-jobs", type=int, choices=range(1, 9),
                        default=2 if sys.platform == "linux" else 1,
                        help="isolated module workers for full self-tests; use 1 for serial debugging")
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 1800:
        parser.error("--timeout-seconds must be from 1 through 1800")
    cancelled = []

    def interrupted(signum, _frame):
        if not cancelled:
            cancelled.append(signum)

    previous = {signum: signal.signal(signum, interrupted)
                for signum in (signal.SIGINT, signal.SIGTERM)}
    try:
        return run_checks(args, cancelled)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
