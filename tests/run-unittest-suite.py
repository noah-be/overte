#!/usr/bin/env python3
"""Run one Python unittest directory, rejecting empty or incomplete selections."""

from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_ids = []
        self.fixture_skips = []

    def startTest(self, test):
        self.executed_ids.append(test.id())
        super().startTest(test)

    def addSkip(self, test, reason):
        # setUpModule/setUpClass may skip a whole fixture without startTest calls.
        # Preserve that documented unittest behavior while accounting for every
        # selected case, instead of treating an early result.stop() as success.
        if not isinstance(test, unittest.TestCase):
            match = re.fullmatch(r"setUp(?:Class|Module) \(([^)]+)\)", test.id())
            if match:
                self.fixture_skips.append(match.group(1))
        super().addSkip(test, reason)


def worker(manifest_path: Path) -> int:
    """Internal worker: execute precisely the cases selected by the parent."""
    # The parent blocks cancellation briefly while registering a spawned PID.
    # That mask survives exec; workers and their children must remain killable.
    signal.pthread_sigmask(signal.SIG_UNBLOCK, (signal.SIGINT, signal.SIGTERM))
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (not isinstance(document, dict)
            or set(document) != {"schema", "module", "ids", "sys_path"}
            or document["schema"] != 1
            or not isinstance(document["module"], str)
            or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", document["module"])
            or not isinstance(document["ids"], list) or not document["ids"]
            or any(not isinstance(item, str) or not item.startswith(document["module"] + ".")
                   for item in document["ids"])
            or not isinstance(document["sys_path"], list)
            or any(not isinstance(item, str) for item in document["sys_path"])):
        raise ValueError("invalid internal unittest worker manifest")
    sys.path[:] = document["sys_path"]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(document["ids"])
    if loader.errors:
        raise RuntimeError("worker test loading failed:\n" + "\n".join(loader.errors))
    loaded = [case.id() for case in cases(suite)]
    if loaded != document["ids"]:
        raise RuntimeError(f"loaded test IDs differ from discovery: expected {document['ids']!r}, got {loaded!r}")
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    fixture_skipped = [identifier for identifier in loaded
                       if any(identifier.startswith(fixture + ".") for fixture in result.fixture_skips)]
    accounted = Counter(result.executed_ids) + Counter(fixture_skipped)
    complete = accounted == Counter(loaded)
    successful = result.wasSuccessful() and complete
    if not complete:
        print("ERROR: selected tests were not completely executed or explicitly skipped", file=sys.stderr)
    report = {
        "schema": 1, "loaded_ids": loaded, "ran": result.testsRun,
        "executed_ids": result.executed_ids, "fixture_skipped_ids": fixture_skipped,
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "successful": successful,
    }
    output = manifest_path.with_suffix(".result.json")
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report), encoding="utf-8")
    temporary.replace(output)
    return 0 if successful else 1


def stop_worker(process: subprocess.Popen) -> None:
    # Each worker owns a new process group. Clean descendants even after a worker
    # exits normally; an uncollected background child must not outlive this run.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def subreaper(enabled: int | None = None) -> int:
    """Keep detached worker descendants owned by this Linux helper process."""
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:  # PR_GET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot read child-subreaper state")
    if enabled is not None and libc.prctl(36, enabled, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot set child-subreaper state")
    return previous.value


def reap_adopted_children() -> None:
    # Only call after every Popen worker has been waited for. A detached daemon
    # can be shared with a still-running worker, and waitpid must not consume a
    # worker's exit status. /proc lists only this process's own adopted children.
    children = Path(f"/proc/self/task/{os.getpid()}/children")
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
            raise RuntimeError("owned unittest descendants did not terminate within cleanup deadline")
        time.sleep(0.01)


class TerminationRequested(BaseException):
    def __init__(self, signum):
        self.signum = signum


def parallel_run(suite, jobs: int, timeout: int, report_path: Path | None = None) -> int:
    groups = OrderedDict()
    for case in cases(suite):
        groups.setdefault(type(case).__module__, []).append(case.id())
    selected = sum(len(ids) for ids in groups.values())
    records = []
    active = []
    previous_handlers = {}
    previous_subreaper = subreaper(1)

    def interrupted(signum, frame):
        raise TerminationRequested(signum)

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, interrupted)
        with tempfile.TemporaryDirectory(prefix="overte-unittest-workers-") as directory:
            root = Path(directory)
            for index, (module, ids) in enumerate(groups.items()):
                manifest = root / f"{index:04d}.json"
                manifest.write_text(json.dumps({
                    "schema": 1, "module": module, "ids": ids, "sys_path": sys.path,
                }), encoding="utf-8")
                records.append({"module": module, "ids": ids, "manifest": manifest,
                                "output": root / f"{index:04d}.log", "error": ""})
            pending = iter(records)
            exhausted = False
            try:
                while active or not exhausted:
                    while len(active) < jobs and not exhausted:
                        record = next(pending, None)
                        if record is None:
                            exhausted = True
                            break
                        # Do not allow cancellation between process creation and
                        # registration for cleanup, including inside Popen itself.
                        mask = signal.pthread_sigmask(signal.SIG_BLOCK, previous_handlers)
                        try:
                            with record["output"].open("wb") as output:
                                record["process"] = subprocess.Popen([
                                    sys.executable, "-u", str(Path(__file__).resolve()),
                                    "--_worker-manifest", str(record["manifest"]),
                                ], stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                            record["started"] = time.monotonic()
                            active.append(record)
                        finally:
                            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
                    for record in active[:]:
                        process = record["process"]
                        if process.poll() is None:
                            if time.monotonic() - record["started"] < timeout:
                                continue
                            record["error"] = f"worker timed out after {timeout}s"
                        stop_worker(process)
                        record["returncode"] = process.returncode
                        active.remove(record)
                    if active:
                        time.sleep(0.02)
            finally:
                # Block a second termination signal from interrupting cleanup.
                for signum in previous_handlers:
                    signal.signal(signum, signal.SIG_IGN)
                for record in active:
                    stop_worker(record["process"])
                reap_adopted_children()
            totals = {"loaded": 0, "ran": 0, "skipped": 0}
            failed = 0
            module_reports = []
            for record in records:
                print(f"\n=== {record['module']} ({len(record['ids'])} selected) ===", file=sys.stderr)
                with record["output"].open(encoding="utf-8", errors="replace") as output:
                    shutil.copyfileobj(output, sys.stderr)
                report = None
                try:
                    report = json.loads(record["manifest"].with_suffix(".result.json").read_text(encoding="utf-8"))
                    if (not isinstance(report, dict) or report.get("schema") != 1
                            or report.get("loaded_ids") != record["ids"]
                            or not isinstance(report.get("successful"), bool)
                            or any(not isinstance(report.get(key), list)
                                   or any(not isinstance(identifier, str) for identifier in report[key])
                                   for key in ("executed_ids", "fixture_skipped_ids"))
                            or any(type(report.get(key)) is not int or report[key] < 0
                                   for key in ("ran", "skipped", "failures", "errors"))
                            or report["ran"] != len(report["executed_ids"])
                            or report["ran"] > len(record["ids"])
                            or (report["successful"]
                                and Counter(report["executed_ids"] + report["fixture_skipped_ids"])
                                != Counter(record["ids"]))):
                        raise ValueError("worker result does not match the selected tests")
                    totals["loaded"] += len(report["loaded_ids"])
                    totals["ran"] += report["ran"]
                    totals["skipped"] += report["skipped"]
                except (OSError, ValueError, TypeError) as error:
                    record["error"] = record["error"] or f"missing or invalid worker result: {error}"
                    report = None
                if record["returncode"] != 0 or record["error"] or not report or not report.get("successful"):
                    failed += 1
                    message = record["error"] or f"worker exited with code {record['returncode']}"
                    print(f"ERROR: {record['module']}: {message} (exit code {record['returncode']})", file=sys.stderr)
                module_reports.append({
                    "module": record["module"], "selected_ids": record["ids"],
                    "result": report, "exit_code": record["returncode"], "error": record["error"],
                })
            print(f"\nParallel unittest: selected={selected}, loaded={totals['loaded']}, "
                  f"ran={totals['ran']}, skipped={totals['skipped']}, "
                  f"modules={len(groups)}, failed_modules={failed}, workers={jobs}", file=sys.stderr)
            if report_path:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = report_path.with_suffix(report_path.suffix + ".tmp")
                temporary.write_text(json.dumps({
                    "schema": 1, "selected": selected, **totals,
                    "failed_modules": failed, "workers": jobs, "modules": module_reports,
                }, indent=2) + "\n", encoding="utf-8")
                temporary.replace(report_path)
            return 1 if failed else 0
    finally:
        try:
            subreaper(previous_subreaper)
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?")
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--jobs", type=int, default=1,
                        help="module worker processes, from 1 (serial) through 8")
    parser.add_argument("--timeout-seconds", type=int, default=900,
                        help="per-worker timeout when --jobs is greater than 1")
    parser.add_argument("--report-json", type=Path,
                        help="write selected and loaded IDs plus results for a parallel run")
    parser.add_argument("--_worker-manifest", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error("--jobs must be from 1 through 8")
    if not 1 <= args.timeout_seconds <= 1800:
        parser.error("--timeout-seconds must be from 1 through 1800")
    if args._worker_manifest:
        if args.directory or args.jobs != 1:
            parser.error("internal worker invocation cannot include discovery options")
        return worker(args._worker_manifest)
    if not args.directory:
        parser.error("directory is required")
    if args.jobs > 1 and not sys.platform.startswith("linux"):
        parser.error("parallel workers require Linux child-subreaper support")
    if args.report_json and args.jobs == 1:
        parser.error("--report-json requires parallel workers (--jobs greater than 1)")
    if args.report_json:
        # A failed/aborted rerun must never leave previous success as its report.
        args.report_json.unlink(missing_ok=True)
    # Match `python -m unittest`: tests may import shared helpers from the
    # repository working directory, not just the selected discovery directory.
    sys.path.insert(0, str(Path.cwd()))
    loader = unittest.TestLoader()
    suite = loader.discover(str(args.directory), pattern=args.pattern)
    if not suite.countTestCases():
        print("ERROR: unittest selection contains no test cases", file=sys.stderr)
        return 1
    if args.jobs == 1:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    if loader.errors:
        print("ERROR: unittest discovery failed:\n" + "\n".join(loader.errors), file=sys.stderr)
        return 1
    try:
        return parallel_run(suite, args.jobs, args.timeout_seconds, args.report_json)
    except TerminationRequested as error:
        print(f"ERROR: unittest workers interrupted by signal {error.signum}", file=sys.stderr)
        return 128 + error.signum


if __name__ == "__main__":
    raise SystemExit(main())
