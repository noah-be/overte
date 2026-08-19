#!/usr/bin/env python3
"""Publish bounded, path-free health telemetry for a iOS CI runner."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any, BinaryIO, Callable


SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SECRET_NAME = re.compile(
    r"(?:token|secret|password|passwd|credential|sign|api.?key|private.?key)", re.I
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?:token|secret|password|passwd|credential|signing|api[_-]?key)"
    r"\s*[:=]\s*)(?:\S+)"
)
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_.-])/(?:[^\s\"'<>|:]+/?)+")


def _command(arguments: list[str]) -> str:
    try:
        return subprocess.run(arguments, capture_output=True, text=True, check=False,
                              timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _mac_memory() -> dict[str, float]:
    page_size_text = _command(["sysctl", "-n", "hw.pagesize"]).strip()
    total_text = _command(["sysctl", "-n", "hw.memsize"]).strip()
    vm = _command(["vm_stat"])
    if not page_size_text.isdigit() or not total_text.isdigit() or not vm:
        return {}
    page_size = int(page_size_text)
    pages: dict[str, int] = {}
    for line in vm.splitlines():
        match = re.match(r"([^:]+):\s*([0-9]+)\.?$", line.strip())
        if match:
            pages[match.group(1)] = int(match.group(2))
    free_pages = sum(pages.get(name, 0) for name in
                     ("Pages free", "Pages inactive", "Pages speculative"))
    total = int(total_text)
    available = min(total, free_pages * page_size)
    result = {
        "ram_total_mib": total / 1048576,
        "ram_available_mib": available / 1048576,
        "ram_available_pct": available * 100 / total if total else 0.0,
        "ram_used_mib": (total - available) / 1048576,
        "ram_used_pct": (total - available) * 100 / total if total else 0.0,
    }
    swap = _command(["sysctl", "-n", "vm.swapusage"])
    match = re.search(r"total\s*=\s*([0-9.]+)M\s+used\s*=\s*([0-9.]+)M", swap)
    if match:
        swap_total, swap_used = map(float, match.groups())
        result.update(swap_total_mib=swap_total, swap_used_mib=swap_used,
                      swap_used_pct=swap_used * 100 / swap_total if swap_total else 0.0)
    pressure = _command(["memory_pressure", "-Q"])
    match = re.search(r"System-wide memory free percentage:\s*([0-9.]+)%", pressure)
    if match:
        result["memory_free_pct"] = float(match.group(1))
    return result


def _linux_memory() -> dict[str, float]:
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            name, value = line.split(":", 1)
            values[name] = int(value.strip().split()[0]) / 1024
    except (OSError, ValueError, IndexError):
        return {}
    total = values.get("MemTotal", 0.0)
    available = values.get("MemAvailable", values.get("MemFree", 0.0))
    swap_total = values.get("SwapTotal", 0.0)
    swap_used = max(0.0, swap_total - values.get("SwapFree", 0.0))
    return {
        "ram_total_mib": total, "ram_available_mib": available,
        "ram_available_pct": available * 100 / total if total else 0.0,
        "ram_used_mib": max(0.0, total - available),
        "ram_used_pct": (total - available) * 100 / total if total else 0.0,
        "swap_total_mib": swap_total, "swap_used_mib": swap_used,
        "swap_used_pct": swap_used * 100 / swap_total if swap_total else 0.0,
    }


def _directory_size(path: Path) -> float:
    # Let the platform utility traverse large Conan/build trees outside the
    # Python telemetry thread.  The bounded command timeout prevents a size
    # sample from delaying the 30-second health channel indefinitely.
    output = _command(["du", "-sk", str(path)])
    try:
        return int(output.split(None, 1)[0]) / 1024
    except (ValueError, IndexError):
        return 0.0


def _cpu_seconds(value: str) -> float:
    """Convert the BSD/Linux ``ps time`` format to seconds."""
    day, separator, clock = value.strip().rpartition("-")
    days = int(day) if separator else 0
    fields = clock.split(":")
    if len(fields) == 2:
        fields.insert(0, "0")
    if len(fields) != 3:
        raise ValueError("invalid process CPU time")
    hours, minutes, seconds = fields
    return days * 86400 + int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _safe_process_name(value: str) -> str:
    name = Path(value.strip()).name[:80]
    clean = re.sub(r"[^A-Za-z0-9_.+-]", "_", name)
    return clean or "unknown"


def _parse_process_snapshot(output: str) -> list[dict[str, Any]]:
    """Parse a deliberately argument-free process image.

    ``comm`` is the final column.  Unlike ``args``, it cannot contain command
    arguments, response-file paths, signing values, or tokens.
    """
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.strip().split(None, 6)
        if len(fields) != 7:
            continue
        try:
            rows.append({
                "pid": int(fields[0]),
                "ppid": int(fields[1]),
                "pgid": int(fields[2]),
                "cpu": _cpu_seconds(fields[3]),
                "rss": int(fields[4]),
                "cpu_pct": float(fields[5].replace(",", ".")),
                "name": _safe_process_name(fields[6]),
            })
        except ValueError:
            continue
    return rows


def _process_snapshot() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["ps", "-ww", "-axo", "pid=,ppid=,pgid=,time=,rss=,%cpu=,comm="],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    rows = _parse_process_snapshot(result.stdout)
    if sys.platform.startswith("linux"):
        # GNU ps rounds TIME to whole seconds.  /proc provides the precision
        # needed by the hermetic short-interval tests and Linux self-hosted use.
        try:
            ticks_per_second = os.sysconf("SC_CLK_TCK")
        except (OSError, ValueError):
            ticks_per_second = 0
        if ticks_per_second:
            for row in rows:
                try:
                    stat = Path(f"/proc/{row['pid']}/stat").read_text()
                    after_name = stat.rsplit(")", 1)[1].split()
                    row["cpu"] = (
                        int(after_name[11]) + int(after_name[12])
                    ) / ticks_per_second
                except (OSError, ValueError, IndexError):
                    pass
    return rows


def _process_scope(rows: list[dict[str, Any]], root: int) -> list[dict[str, Any]]:
    """Return the launch process group plus descendants that changed groups."""
    selected = {root}
    selected.update(int(row["pid"]) for row in rows if int(row["pgid"]) == root)
    changed = True
    while changed:
        changed = False
        for row in rows:
            pid = int(row["pid"])
            if int(row["ppid"]) in selected and pid not in selected:
                selected.add(pid)
                changed = True
    return [row for row in rows if int(row["pid"]) in selected]


def _sanitize_diagnostic(text: str) -> str:
    for name, value in os.environ.items():
        if value and len(value) >= 4 and SECRET_NAME.search(name):
            text = text.replace(value, "<redacted-secret>")
    safe_lines = []
    for line in text.splitlines(keepends=True):
        # Stack traces are useful, raw argv and environment dumps are not.
        if re.match(r"\s*(?:arguments?|command line|environment)(?:\s|:|=)", line, re.I):
            safe_lines.append("<redacted-process-context>\n")
        else:
            safe_lines.append(line)
    text = "".join(safe_lines)
    text = SECRET_ASSIGNMENT.sub(r"\1<redacted-secret>", text)
    return ABSOLUTE_PATH.sub("<redacted-path>", text)


def _write_private(path: Path, contents: str) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, contents.encode("utf-8", "replace"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _collect_phase_diagnostics(directory: Path | None, phase: str, invocation: str,
                               rows: list[dict[str, Any]]) -> None:
    if directory is None:
        return
    try:
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    except OSError:
        return
    safe_rows = [
        {key: row[key] for key in ("pid", "ppid", "pgid", "cpu", "cpu_pct", "rss", "name")}
        for row in rows
    ]
    report = {
        "phase": phase,
        "id": invocation,
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "processes": safe_rows,
    }
    try:
        _write_private(
            directory / f"stall-{phase}-{invocation}.json",
            json.dumps(report, indent=2, sort_keys=True) + "\n",
        )
    except OSError:
        pass

    sample = shutil.which("sample")
    if not sample:
        return
    # A bounded selection keeps diagnostics useful without delaying termination
    # for every helper in a large dependency process tree.
    targets = sorted(
        rows,
        key=lambda row: (float(row.get("cpu_pct", 0.0)), int(row.get("rss", 0))),
        reverse=True,
    )[:3]
    for row in targets:
        pid = int(row["pid"])
        try:
            result = subprocess.run(
                [sample, str(pid), "3", "1"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            contents = result.stdout + result.stderr
        except (OSError, subprocess.TimeoutExpired) as error:
            contents = f"sample unavailable: {type(error).__name__}\n"
        try:
            _write_private(
                directory / f"sample-{phase}-{invocation}-{pid}.txt",
                _sanitize_diagnostic(contents),
            )
        except OSError:
            pass


def _signal_group(pid: int, signum: int) -> None:
    try:
        os.killpg(pid, signum)
    except (ProcessLookupError, PermissionError):
        pass


def _terminate_group(process: subprocess.Popen[bytes], grace: float) -> None:
    _signal_group(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    # Descendants may outlive the group leader, so always escalate the group.
    _signal_group(process.pid, signal.SIGKILL)
    if process.poll() is None:
        process.wait()


def _terminate_process(process: subprocess.Popen[bytes], grace: float) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class Collector:
    def __init__(self, disk_path: Path, directories: dict[str, Path]):
        self.disk_path = disk_path
        self.directories = directories

    def sample(self, include_directories: bool = False) -> tuple[dict[str, float], dict[str, float]]:
        metrics: dict[str, float] = {}
        try:
            load1, load5, load15 = os.getloadavg()
            metrics.update(load_1m=load1, load_5m=load5, load_15m=load15)
            cpu_count = os.cpu_count() or 1
            metrics.update(cpu_count=float(cpu_count), load_1m_per_cpu=load1 / cpu_count)
        except OSError:
            pass
        cpu_text = _command(["ps", "-A", "-o", "%cpu="])
        cpu_values = []
        for value in cpu_text.splitlines():
            try:
                cpu_values.append(float(value.strip().replace(",", ".")))
            except ValueError:
                pass
        metrics["cpu_activity_pct"] = sum(cpu_values)
        process_text = _command(["ps", "-A", "-o", "pid="])
        metrics["process_count"] = float(sum(1 for line in process_text.splitlines() if line.strip()))
        metrics.update(_mac_memory() if sys.platform == "darwin" else _linux_memory())
        try:
            usage = shutil.disk_usage(self.disk_path)
            metrics.update(disk_total_mib=usage.total / 1048576,
                           disk_free_mib=usage.free / 1048576,
                           disk_used_pct=usage.used * 100 / usage.total if usage.total else 0.0)
            stat = os.statvfs(self.disk_path)
            if stat.f_files:
                metrics["inode_free"] = float(stat.f_favail)
                metrics["inode_used_pct"] = (stat.f_files - stat.f_favail) * 100 / stat.f_files
        except OSError:
            pass
        sizes = ({label: _directory_size(path) for label, path in self.directories.items()}
                 if include_directories else {})
        return metrics, sizes


class Aggregator:
    def __init__(self) -> None:
        self.values: dict[str, list[float]] = {}

    def add(self, metrics: dict[str, float]) -> None:
        for name, value in metrics.items():
            if isinstance(value, (int, float)) and math.isfinite(value):
                self.values.setdefault(name, []).append(float(value))

    def report(self) -> dict[str, dict[str, float]]:
        result = {}
        for name, values in sorted(self.values.items()):
            result[name] = {"current": round(values[-1], 2), "min": round(min(values), 2),
                            "max": round(max(values), 2),
                            "avg": round(sum(values) / len(values), 2)}
        return result

    def clear(self) -> None:
        self.values.clear()


class Emitter:
    def __init__(self, log_path: Path | None, stream=sys.stdout):
        self.log_path = log_path
        self.stream = stream

    def __call__(self, event: str, **fields: object) -> None:
        record = {
            "ios_runner_telemetry": event,
            "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        record.update(fields)
        line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        if self.log_path:
            try:
                descriptor = os.open(
                    self.log_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
                )
                try:
                    os.fchmod(descriptor, 0o600)
                    os.write(descriptor, line.encode())
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError as error:
                record["append_error"] = type(error).__name__
                line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        try:
            self.stream.write(line)
            self.stream.flush()
        except (BrokenPipeError, OSError):
            pass


def _alerts(metrics: dict[str, float], disk_free_mib: float,
            memory_available_pct: float, swap_used_pct: float) -> set[str]:
    alerts = set()
    if metrics.get("disk_free_mib", float("inf")) < disk_free_mib:
        alerts.add("disk_free_low")
    if metrics.get("ram_available_pct", 100.0) < memory_available_pct:
        alerts.add("memory_available_low")
    if metrics.get("swap_used_pct", 0.0) > swap_used_pct:
        alerts.add("swap_usage_high")
    return alerts


def run(collector: Collector, emit: Callable[..., None], sample_seconds: float,
        report_seconds: float, directory_seconds: float, disk_free_mib: float,
        memory_available_pct: float, swap_used_pct: float,
        max_samples: int | None = None, clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        stopping: Callable[[], bool] = lambda: False) -> None:
    aggregate = Aggregator()
    started = clock()
    next_report = started + report_seconds
    next_directory = started
    latest_sizes: dict[str, float] = {}
    prior_alerts: set[str] = set()
    samples = 0
    emit("start", sample_seconds=sample_seconds, report_seconds=report_seconds,
         directory_seconds=directory_seconds)
    while not stopping() and (max_samples is None or samples < max_samples):
        now = clock()
        include_directories = now >= next_directory
        metrics, sizes = collector.sample(include_directories)
        aggregate.add(metrics)
        samples += 1
        current_alerts = _alerts(metrics, disk_free_mib, memory_available_pct, swap_used_pct)
        for alert in sorted(current_alerts - prior_alerts):
            emit("threshold", state="active", condition=alert)
        for alert in sorted(prior_alerts - current_alerts):
            emit("threshold", state="recovered", condition=alert)
        prior_alerts = current_alerts
        if include_directories:
            latest_sizes = sizes
            next_directory = now + directory_seconds
        if now >= next_report:
            fields: dict[str, object] = {"samples": samples, "metrics": aggregate.report()}
            if latest_sizes:
                fields["directory_mib"] = {
                    name: round(value, 2) for name, value in sorted(latest_sizes.items())
                }
            emit("report", **fields)
            aggregate.clear()
            next_report = now + report_seconds
        if max_samples is None or samples < max_samples:
            sleep(max(0.0, sample_seconds - (clock() - now)))
    emit("end", samples=samples)


class OutputActivity:
    """Forward child output unchanged while exposing only byte activity."""

    def __init__(self, started: float):
        self._lock = threading.Lock()
        self._bytes = 0
        self._last_at = started

    def observe(self, size: int, now: float) -> None:
        with self._lock:
            self._bytes += size
            self._last_at = now

    def snapshot(self) -> tuple[int, float]:
        with self._lock:
            return self._bytes, self._last_at


def _forward_output(stream: BinaryIO, activity: OutputActivity,
                    output_log: BinaryIO | None = None) -> None:
    destination = getattr(sys.stdout, "buffer", sys.stdout)
    while True:
        try:
            chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536)
        except (OSError, ValueError):
            break
        if not chunk:
            break
        activity.observe(len(chunk), time.monotonic())
        if output_log is not None:
            try:
                output_log.write(chunk)
                output_log.flush()
            except (BrokenPipeError, OSError, ValueError):
                # The live build must continue even if its supplementary raw
                # log cannot be written. The telemetry channel records the
                # phase result independently.
                output_log = None
        try:
            destination.write(chunk)
            destination.flush()
        except (BrokenPipeError, OSError):
            # Continue draining so a closed log consumer cannot deadlock the
            # supervised command's stdout pipe.
            continue


def supervise(command: list[str], collector: Collector, emit: Callable[..., None],
              phase: str, sample_seconds: float, report_seconds: float,
              directory_seconds: float, inactivity_timeout: float,
              monitor_failure_timeout: float, term_grace: float,
              disk_free_mib: float, memory_available_pct: float,
              swap_used_pct: float, diagnostics_dir: Path | None,
              compiler_live_log: Path | None = None,
              compiler_diagnostics_dir: Path | None = None,
              max_runtime: float | None = None,
              output_log: Path | None = None) -> int:
    """Run one non-compiler phase with resource-aware stall detection."""
    started = time.monotonic()
    invocation = secrets.token_hex(6)
    child_env = os.environ.copy()
    tail: subprocess.Popen[bytes] | None = None
    if compiler_live_log is not None:
        try:
            compiler_live_log.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                compiler_live_log, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
            )
            try:
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as error:
            emit(
                "start", phase=phase, id=invocation, pid=0,
                sample_seconds=sample_seconds, report_seconds=report_seconds,
                inactivity_timeout_seconds=inactivity_timeout,
            )
            emit(
                "end", phase=phase, id=invocation,
                elapsed_s=round(time.monotonic() - started, 1), samples=0,
                exit_code=125, reason="live_channel_failure",
                error=type(error).__name__,
            )
            return 125
        child_env["OVERTE_COMPILER_WATCHDOG_LOG"] = str(compiler_live_log)
        try:
            # This channel bypasses CMake/Ninja/Conan stdout buffering. Starting
            # at EOF preserves append-only history without replaying old runs.
            tail = subprocess.Popen(["tail", "-n", "0", "-F", str(compiler_live_log)])
        except OSError as error:
            emit(
                "start", phase=phase, id=invocation, pid=0,
                sample_seconds=sample_seconds, report_seconds=report_seconds,
                inactivity_timeout_seconds=inactivity_timeout,
            )
            emit(
                "end", phase=phase, id=invocation,
                elapsed_s=round(time.monotonic() - started, 1), samples=0,
                exit_code=125, reason="live_tail_failure",
                error=type(error).__name__,
            )
            return 125
    if compiler_diagnostics_dir is not None:
        try:
            compiler_diagnostics_dir.mkdir(parents=True, exist_ok=True)
            compiler_diagnostics_dir.chmod(0o700)
        except OSError as error:
            emit(
                "start", phase=phase, id=invocation, pid=0,
                sample_seconds=sample_seconds, report_seconds=report_seconds,
                inactivity_timeout_seconds=inactivity_timeout,
            )
            emit(
                "end", phase=phase, id=invocation,
                elapsed_s=round(time.monotonic() - started, 1), samples=0,
                exit_code=125, reason="diagnostics_setup_failure",
                error=type(error).__name__,
            )
            if tail is not None:
                _terminate_process(tail, 1.0)
            return 125
        child_env["OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS"] = str(
            compiler_diagnostics_dir
        )
    raw_output: BinaryIO | None = None
    if output_log is not None:
        try:
            output_log.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                output_log, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
            )
            os.fchmod(descriptor, 0o600)
            raw_output = os.fdopen(descriptor, "ab", buffering=0)
        except OSError as error:
            emit("end", phase=phase, id=invocation, elapsed_s=0.0, samples=0,
                 exit_code=125, reason="output_log_failure",
                 error=type(error).__name__)
            if tail is not None:
                _terminate_process(tail, 1.0)
            return 125
    try:
        process: subprocess.Popen[bytes] = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=child_env,
        )
    except OSError as error:
        emit(
            "start", phase=phase, id=invocation, pid=0,
            sample_seconds=sample_seconds, report_seconds=report_seconds,
            inactivity_timeout_seconds=inactivity_timeout,
        )
        emit(
            "end", phase=phase, id=invocation,
            elapsed_s=round(time.monotonic() - started, 1), samples=0,
            exit_code=127, reason="launch_failure", error=type(error).__name__,
        )
        if tail is not None:
            _terminate_process(tail, 1.0)
        if raw_output is not None:
            raw_output.close()
        return 127
    assert process.stdout is not None
    activity = OutputActivity(started)
    reader = threading.Thread(
        target=_forward_output,
        args=(process.stdout, activity, raw_output),
        name="phase-output",
        daemon=True,
    )
    reader.start()

    aggregate = Aggregator()
    next_sample = started
    next_report = started + report_seconds
    next_directory = started
    last_progress = started
    last_cpu: dict[int, float] = {}
    last_output_bytes = 0
    last_sizes: dict[str, float] = {}
    latest_sizes: dict[str, float] = {}
    progress_sources: set[str] = set()
    prior_alerts: set[str] = set()
    monitor_failure_started: float | None = None
    monitor_error_name = ""
    forwarded_signal = 0
    signal_deadline = 0.0
    latest_rows: list[dict[str, Any]] = []
    samples = 0

    def forward_signal(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal, signal_deadline
        if not forwarded_signal:
            forwarded_signal = signum
            signal_deadline = time.monotonic() + term_grace
        _signal_group(process.pid, signum)

    old_term = signal.signal(signal.SIGTERM, forward_signal)
    old_int = signal.signal(signal.SIGINT, forward_signal)
    emit(
        "start",
        phase=phase,
        id=invocation,
        pid=process.pid,
        sample_seconds=sample_seconds,
        report_seconds=report_seconds,
        inactivity_timeout_seconds=inactivity_timeout,
        max_runtime_seconds=max_runtime,
    )
    reason = "exit"
    result_code = 0
    try:
        while True:
            now = time.monotonic()
            status = process.poll()

            # The phase wall deadline is fail-closed.  Check it before a
            # concurrently observed child exit so a process that finishes
            # while timeout diagnostics are being scheduled cannot turn an
            # already-expired phase into a false success.  Processes observed
            # before the deadline still preserve their real exit status below.
            if max_runtime is not None and now - started >= max_runtime:
                emit(
                    "timed_out",
                    phase=phase,
                    id=invocation,
                    elapsed_s=round(now - started, 1),
                    limit_s=round(max_runtime, 1),
                )
                _collect_phase_diagnostics(
                    diagnostics_dir, phase, invocation, latest_rows
                )
                if process.poll() is None:
                    _terminate_group(process, term_grace)
                result_code = 124
                reason = "wall_timeout"
                break

            if forwarded_signal:
                if now >= signal_deadline:
                    _signal_group(process.pid, signal.SIGKILL)
                    signal_deadline = float("inf")
                if status is not None and signal_deadline == float("inf"):
                    result_code = 128 + forwarded_signal
                    reason = "signal"
                    break
            elif status is not None:
                result_code = 128 - status if status < 0 else status
                break

            if now >= next_sample and status is None:
                include_directories = now >= next_directory
                metrics, sizes = collector.sample(include_directories)
                aggregate.add(metrics)
                samples += 1
                current_alerts = _alerts(
                    metrics, disk_free_mib, memory_available_pct, swap_used_pct
                )
                for alert in sorted(current_alerts - prior_alerts):
                    emit("threshold", phase=phase, id=invocation,
                         state="active", condition=alert)
                for alert in sorted(prior_alerts - current_alerts):
                    emit("threshold", phase=phase, id=invocation,
                         state="recovered", condition=alert)
                prior_alerts = current_alerts
                if include_directories:
                    latest_sizes = sizes
                    if any(
                        last_sizes.get(label, 0.0) != size for label, size in sizes.items()
                    ):
                        last_progress = now
                        progress_sources.add("filesystem")
                    last_sizes = dict(sizes)
                    next_directory = now + directory_seconds

                try:
                    rows = _process_scope(_process_snapshot(), process.pid)
                    if not rows and process.poll() is None:
                        raise RuntimeError("empty process scope")
                    latest_rows = rows
                    cpu_progress = False
                    current_cpu: dict[int, float] = {}
                    for row in rows:
                        pid = int(row["pid"])
                        cpu = float(row["cpu"])
                        current_cpu[pid] = cpu
                        previous = last_cpu.get(pid)
                        if (previous is not None and cpu > previous + 0.001) or (
                            previous is None and cpu > 0.0
                        ):
                            cpu_progress = True
                    last_cpu = current_cpu
                    if cpu_progress:
                        last_progress = now
                        progress_sources.add("cpu")
                    aggregate.add({
                        "phase_cpu_seconds": sum(float(row["cpu"]) for row in rows),
                        "phase_cpu_activity_pct": sum(
                            float(row["cpu_pct"]) for row in rows
                        ),
                        "phase_rss_mib": sum(int(row["rss"]) for row in rows) / 1024,
                        "phase_process_count": float(len(rows)),
                    })
                    if monitor_failure_started is not None:
                        emit("monitor_recovered", phase=phase, id=invocation,
                             error=monitor_error_name)
                    monitor_failure_started = None
                    monitor_error_name = ""
                except Exception as error:  # monitoring must not hide the child failure
                    error_name = type(error).__name__
                    if monitor_failure_started is None:
                        monitor_failure_started = now
                        monitor_error_name = error_name
                        emit("monitor_error", phase=phase, id=invocation,
                             error=error_name)

                output_bytes, output_at = activity.snapshot()
                if output_bytes != last_output_bytes:
                    last_output_bytes = output_bytes
                    last_progress = max(last_progress, output_at)
                    progress_sources.add("output")

                idle = max(0.0, now - last_progress)
                if monitor_failure_started is not None:
                    monitor_idle = now - monitor_failure_started
                    if monitor_idle >= monitor_failure_timeout:
                        _collect_phase_diagnostics(
                            diagnostics_dir, phase, invocation, latest_rows
                        )
                        status = process.poll()
                        if status is not None:
                            result_code = 128 - status if status < 0 else status
                            reason = "signal" if forwarded_signal else "exit"
                            if forwarded_signal:
                                result_code = 128 + forwarded_signal
                            break
                        emit(
                            "monitor_failed",
                            phase=phase,
                            id=invocation,
                            elapsed_s=round(now - started, 1),
                            unavailable_s=round(monitor_idle, 1),
                            error=monitor_error_name,
                        )
                        _terminate_group(process, term_grace)
                        result_code = 128 + forwarded_signal if forwarded_signal else 125
                        reason = "signal" if forwarded_signal else "monitor_failure"
                        break
                elif idle >= inactivity_timeout:
                    _collect_phase_diagnostics(diagnostics_dir, phase, invocation, latest_rows)
                    status = process.poll()
                    if status is not None:
                        result_code = 128 - status if status < 0 else status
                        reason = "signal" if forwarded_signal else "exit"
                        if forwarded_signal:
                            result_code = 128 + forwarded_signal
                        break
                    emit(
                        "stalled",
                        phase=phase,
                        id=invocation,
                        elapsed_s=round(now - started, 1),
                        inactive_s=round(idle, 1),
                    )
                    _terminate_group(process, term_grace)
                    result_code = 128 + forwarded_signal if forwarded_signal else 124
                    reason = "signal" if forwarded_signal else "inactivity"
                    break
                next_sample = now + sample_seconds

            now = time.monotonic()
            if now >= next_report and process.poll() is None:
                output_bytes, _output_at = activity.snapshot()
                fields: dict[str, object] = {
                    "phase": phase,
                    "id": invocation,
                    "elapsed_s": round(now - started, 1),
                    "inactive_s": round(max(0.0, now - last_progress), 1),
                    "samples": samples,
                    "metrics": aggregate.report(),
                    "output_bytes": output_bytes,
                    "progress_sources": sorted(progress_sources),
                }
                if latest_sizes:
                    fields["directory_mib"] = {
                        name: round(value, 2)
                        for name, value in sorted(latest_sizes.items())
                    }
                if monitor_failure_started is not None:
                    fields["monitor_unavailable_s"] = round(
                        now - monitor_failure_started, 1
                    )
                emit("heartbeat", **fields)
                aggregate.clear()
                progress_sources.clear()
                next_report = now + report_seconds

            # Keep signal escalation responsive without busy polling.
            wake_at = min(next_sample, next_report)
            if forwarded_signal:
                wake_at = min(wake_at, signal_deadline)
            time.sleep(max(0.01, min(0.1, wake_at - time.monotonic())))
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
        reader.join(timeout=1.0)
        try:
            process.stdout.close()
        except OSError:
            pass
        if reader.is_alive():
            reader.join(timeout=0.2)
        if raw_output is not None:
            raw_output.close()

    if process.poll() is None:
        process.wait()
    emit(
        "end",
        phase=phase,
        id=invocation,
        elapsed_s=round(time.monotonic() - started, 1),
        samples=samples,
        exit_code=result_code,
        reason=reason,
    )
    if tail is not None:
        # Give tail one scheduling quantum to forward the watchdog's final line.
        time.sleep(0.05)
        _terminate_process(tail, 1.0)
    return result_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path)
    parser.add_argument("--phase", default="phase")
    parser.add_argument("--diagnostics-dir", type=Path)
    parser.add_argument("--compiler-live-log", type=Path)
    parser.add_argument("--compiler-diagnostics-dir", type=Path)
    parser.add_argument("--output-log", type=Path)
    parser.add_argument("--disk-path", type=Path, default=Path.cwd())
    parser.add_argument("--watch", "--directory", dest="directories", action="append",
                        default=[], metavar="LABEL=PATH")
    parser.add_argument("--sample-interval", "--sample-seconds", dest="sample_seconds",
                        type=float, default=5.0)
    parser.add_argument("--publish-interval", "--report-seconds", dest="report_seconds",
                        type=float, default=30.0)
    parser.add_argument("--directory-interval", "--directory-seconds", dest="directory_seconds",
                        type=float, default=300.0)
    parser.add_argument("--disk-free-warning-mib", type=float, default=4096.0)
    parser.add_argument("--memory-available-warning-pct", type=float, default=10.0)
    parser.add_argument("--swap-used-warning-pct", type=float, default=80.0)
    parser.add_argument("--inactivity-timeout", type=float, default=1200.0)
    parser.add_argument(
        "--max-runtime", type=float,
        help="controlled wall-clock limit below the surrounding CI step timeout",
    )
    parser.add_argument("--monitor-failure-timeout", type=float, default=120.0)
    parser.add_argument("--term-grace", type=float, default=10.0)
    parser.add_argument("--max-samples", type=int, help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if min(args.sample_seconds, args.report_seconds, args.directory_seconds) <= 0:
        parser.error("sampling intervals must be positive")
    if (args.inactivity_timeout <= 0 or args.monitor_failure_timeout <= 0
            or (args.max_runtime is not None and args.max_runtime <= 0)
            or args.term_grace < 0):
        parser.error("watchdog timeouts must be positive and grace non-negative")
    if not SAFE_LABEL.fullmatch(args.phase):
        parser.error("--phase must be a safe label")
    directories = {}
    for item in args.directories:
        label, separator, path = item.partition("=")
        if not separator or not SAFE_LABEL.fullmatch(label) or not path:
            parser.error("--directory must be a safe LABEL=PATH pair")
        directories[label] = Path(path)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    collector = Collector(args.disk_path, directories)
    emitter = Emitter(args.log)
    if not command:
        stopped = threading.Event()
        forwarded_signal = 0

        def stop(signum: int, _frame: object) -> None:
            nonlocal forwarded_signal
            forwarded_signal = forwarded_signal or signum
            stopped.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        run(collector, emitter, args.sample_seconds, args.report_seconds,
            args.directory_seconds, args.disk_free_warning_mib,
            args.memory_available_warning_pct, args.swap_used_warning_pct,
            args.max_samples, sleep=stopped.wait, stopping=stopped.is_set)
        return 128 + forwarded_signal if forwarded_signal else 0
    diagnostics_dir = args.diagnostics_dir
    if diagnostics_dir is None and os.environ.get("OVERTE_RUNNER_TELEMETRY_DIAGNOSTICS"):
        diagnostics_dir = Path(os.environ["OVERTE_RUNNER_TELEMETRY_DIAGNOSTICS"])
    return supervise(
        command,
        collector,
        emitter,
        args.phase,
        args.sample_seconds,
        args.report_seconds,
        args.directory_seconds,
        args.inactivity_timeout,
        args.monitor_failure_timeout,
        args.term_grace,
        args.disk_free_warning_mib,
        args.memory_available_warning_pct,
        args.swap_used_warning_pct,
        diagnostics_dir,
        args.compiler_live_log,
        args.compiler_diagnostics_dir,
        args.max_runtime,
        args.output_log,
    )


if __name__ == "__main__":
    raise SystemExit(main())
