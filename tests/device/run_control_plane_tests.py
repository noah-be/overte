#!/usr/bin/env python3
"""Hardware-free CI gate for the complete portable device E2E control plane."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import json
import os
import re
from pathlib import Path
import shutil
import signal
import stat
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
        artifact_identity = [sys.executable, "tests/run-unittest-suite.py",
                             "tests/device/schema/artifact-identity"]
        if sys.platform == "linux":
            artifact_identity = [sys.executable, "-I", "-S", "-B",
                                 "tests/device/run_artifact_identity.py"]
        checks.append(("artifact-identity", artifact_identity, False))
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
            ("joint-pending-flags", "world-entry/test_joint_pending_flags.py"),
        ):
            checks.append((name, [sys.executable, str(ROOT / "contracts" / path)], False))
        # Portable production regressions require Qt6 Core/Concurrent/Gui development
        # packages and a host C++ compiler; no device or native client build.
        for path in (
            "audio/test_audio_device_selection.py",
            "audio/test_injector_buffer_publication.py",
            "audio/test_injector_event_delivery.py",
            "audio/test_injector_preparation_lifetime.py",
            "audio/test_recording_safety.py",
            "audio/test_output_pull_lifetime.py",
            "audio/test_sample_sound_controls.py",
            "dependency/test_cache.py",
            "tablet/test_tablet_qml.py",
            "tablet/test_tablet_close.py",
            "lifecycle/test_domain_list_history.py",
            "lifecycle/test_domain_list_receiver.py",
            "lifecycle/test_v8_wrapper_teardown.py",
            "lifecycle/test_entity_script_unload_scope.py",
            "input/test_mobile_world_tap.py",
            "lifecycle/test_qml_wrapper_thread.py",
            "lifecycle/test_qml_property_dispatch.py",
            "graphics/entity-change-thread-test.py",
            "graphics/image-decode-budget-test.py",
            "graphics/image-decode-qt-codec-test.py",
            "graphics/draw-info-object-index-test.py",
        ):
            checks.append((Path(path).stem, [sys.executable, str(ROOT / "contracts" / path)], False))
        # Platform declarations bind prepared-host regressions to their owning
        # product. Shared and Android integration profiles retain portable tests.
        source_profile = json.loads(
            (REPOSITORY / "tests/platform-profile.json").read_text())
        for entry in source_profile["suites"]:
            if entry["name"] == "phone-e2e-runtime-regressions":
                expected = "android/phone/tests/phone-e2e-runtime-regressions.py"
                if (source_profile["platform"] != "android"
                        or entry["entrypoint"] != expected
                        or entry["interpreter"] != "python"
                        or not (REPOSITORY / expected).is_file()):
                    raise ValueError("invalid Phone prepared-host contract declaration")
                checks.append(("phone-native-runtime", [sys.executable,
                               str(REPOSITORY / expected), "--execute"], False))
    else:
        patterns = [
            "test_common_contracts.py", "test_governance_and_frontier.py",
            "test_execution_plan_pipeline.py", "test_harness.py",
            "test_matrix_evaluator.py", "test_voice_peer.py", "test_voice_roundtrip.py",
            "test_web_parity_fixture.py",
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


@contextmanager
def command_owner():
    """Adopt escaped descendants even when a nested scheduler is force-killed."""
    if not sys.platform.startswith("linux"):
        yield lambda: None
        return
    # Keep each CLI self-contained for its existing sparse/bootstrap checkouts.
    children = Path(f"/proc/self/task/{os.getpid()}/children")
    # These standalone CLIs must own every child created in this scope. An
    # existing child could later exit and hand us unrelated grandchildren; a
    # concurrent thread could create unrelated children after any snapshot.
    tasks = {task.name for task in Path("/proc/self/task").iterdir()}
    if tasks != {str(os.getpid())} or children.read_text().split():
        raise RuntimeError("command ownership requires a child-free single-threaded process")
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "cannot read child-subreaper state")
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "cannot set child-subreaper state")

    def reap():
        # The immediate Popen child must already be waited for. The checked
        # standalone scope owns all remaining adopted children.
        deadline = time.monotonic() + 1
        while True:
            owned = [int(pid) for pid in children.read_text().split()]
            if not owned:
                return
            for pid in owned:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for pid in owned:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            if time.monotonic() >= deadline:
                raise RuntimeError("owned command descendants did not terminate within cleanup deadline")
            time.sleep(0.01)

    try:
        yield reap
    finally:
        try:
            reap()
        finally:
            if libc.prctl(36, previous.value, 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "cannot restore child-subreaper state")


def stop_process(process: subprocess.Popen, reap) -> str:
    # Allow the nested scheduler to clean up cooperatively. If it cannot,
    # this runner retains ownership of its descendants through forced exit.
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
        process.wait()
        # Escaped descendants may still hold stdout open after scheduler death.
        reap()
        output, _ = process.communicate()
    return output


def run_command(command: list[str], timeout: int, cancelled: list[int]) -> tuple[int, str, str]:
    with command_owner() as reap:
        return run_owned_command(command, timeout, cancelled, reap)


def run_owned_command(command, timeout, cancelled, reap):
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
                return (128 + cancelled[0], stop_process(process, reap),
                        f"interrupted by signal {cancelled[0]}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return 1, stop_process(process, reap), f"timeout after {timeout}s"
            try:
                output, _ = process.communicate(timeout=min(0.1, remaining))
                if cancelled:
                    return (128 + cancelled[0], stop_process(process, reap),
                            f"interrupted by signal {cancelled[0]}")
                return process.returncode, output, ""
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        stop_process(process, reap)
        raise


def python_failure_diagnostic(item, started_ns):
    """Bounded diagnostic only; this report grants no test-result authority."""
    duration = item["durationSeconds"]
    value = {"kind": "device-python-failure",
             "message": ("timeout" if re.fullmatch(r"timeout after [1-9][0-9]*s", item["message"])
                         else "interrupted" if re.fullmatch(r"interrupted by signal [1-9][0-9]*", item["message"])
                         else "failed"),
             "seconds": round(duration, 3) if type(duration) in (int, float) and 0 <= duration <= 1_000_000 else None,
             "report": "unavailable", "failed": None, "modules": [], "omitted": None, "truncated": False}
    directories = []
    try:
        if type(started_ns) is not int or started_ns <= 0:
            raise ValueError("missing diagnostic start")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        directories.append(os.open(REPOSITORY, flags))
        for name in ("build", "test-results"):
            directories.append(os.open(name, flags, dir_fd=directories[-1]))
        descriptor = os.open("device-self-tests.json",
                             os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=directories[-1])
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or not 0 < before.st_size <= 4 * 1024 * 1024
                    or before.st_mtime_ns < started_ns):
                raise ValueError("unavailable diagnostic report")
            raw = stream.read(4 * 1024 * 1024 + 1)
            after = os.fstat(stream.fileno())
            identity = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                                     info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if identity(before) != identity(after) or len(raw) != before.st_size:
                raise ValueError("diagnostic report changed")
        document = json.loads(raw)
        counters = ("selected", "loaded", "ran", "skipped", "failed_modules")
        if (type(document) is not dict
                or set(document) != {"schema", "selected", "loaded", "ran", "skipped", "failed_modules", "workers", "modules"}
                or document["schema"] != 1
                or any(type(document[key]) is not int or not 0 <= document[key] <= 100_000 for key in counters)
                or type(document["workers"]) is not int or not 2 <= document["workers"] <= 8
                or type(document["modules"]) is not list or not 0 < len(document["modules"]) <= 256):
            raise ValueError("invalid diagnostic shape")
        failed, selected, seen = [], 0, set()
        for row in document["modules"]:
            if (type(row) is not dict or set(row) != {"module", "selected_ids", "result", "exit_code", "error"}
                    or type(row["module"]) is not str or len(row["module"]) > 160
                    or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", row["module"], re.ASCII)
                    or row["module"] in seen or type(row["exit_code"]) is not int
                    or type(row["error"]) is not str or type(row["selected_ids"]) is not list
                    or not 0 < len(row["selected_ids"]) <= 100_000
                    or any(type(identifier) is not str or len(identifier) > 512 for identifier in row["selected_ids"])
                    or (row["result"] is not None
                        and (type(row["result"]) is not dict or row["result"].get("schema") != 1
                             or type(row["result"].get("successful")) is not bool))):
                raise ValueError("invalid diagnostic module")
            seen.add(row["module"])
            selected += len(row["selected_ids"])
            if row["exit_code"] != 0 or row["error"] or row["result"] is None or not row["result"]["successful"]:
                failed.append(row["module"].rsplit(".", 1)[-1])
        if selected != document["selected"] or len(failed) != document["failed_modules"]:
            raise ValueError("inconsistent diagnostic counts")
        names = [name if len(name) <= 48 else name[:47] + "~" for name in failed[:4]]
        value.update(report="ok", failed=len(failed), modules=names, omitted=len(failed) - len(names),
                     truncated=len(failed) > len(names) or any(len(name) > 48 for name in failed[:4]))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        pass
    finally:
        for descriptor in reversed(directories):
            try:
                os.close(descriptor)
            except OSError:
                pass
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    while len(encoded) > 450 and value["modules"]:
        value["modules"].pop()
        value["omitted"] += 1
        value["truncated"] = True
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return encoded


def run_checks(args: argparse.Namespace, cancelled: list[int]) -> int:
    results = []
    python_started_ns = None
    started = time.monotonic()
    for name, command, qml in commands(args.profile, args.self_test_jobs):
        if name == "python-self-tests":
            python_started_ns = time.time_ns() if args.self_test_jobs > 1 else None
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
    if failed:
        print("Device control plane failed groups: " + json.dumps(
            [item["name"] for item in results if item["status"] == "failed"], ensure_ascii=True))
    python_failure = next((item for item in results
                           if item["name"] == "python-self-tests" and item["status"] == "failed"), None)
    if python_failure is not None:
        print(python_failure_diagnostic(python_failure, python_started_ns))
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
