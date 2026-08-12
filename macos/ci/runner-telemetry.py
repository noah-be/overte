#!/usr/bin/env python3
"""Publish bounded, path-free health telemetry for a macOS CI runner."""

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
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Callable, Iterable


SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


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
            "macos_runner_telemetry": event,
            "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        record.update(fields)
        line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        if self.log_path:
            descriptor = os.open(self.log_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.fchmod(descriptor, 0o600)
                os.write(descriptor, line.encode())
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        self.stream.write(line)
        self.stream.flush()


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path)
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
    parser.add_argument("--max-samples", type=int, help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if min(args.sample_seconds, args.report_seconds, args.directory_seconds) <= 0:
        parser.error("sampling intervals must be positive")
    directories = {}
    for item in args.directories:
        label, separator, path = item.partition("=")
        if not separator or not SAFE_LABEL.fullmatch(label) or not path:
            parser.error("--directory must be a safe LABEL=PATH pair")
        directories[label] = Path(path)
    stopped = threading.Event()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    process: subprocess.Popen[bytes] | None = None
    forwarded_signal = 0

    def stop(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal
        forwarded_signal = forwarded_signal or signum
        stopped.set()
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    collector = Collector(args.disk_path, directories)
    emitter = Emitter(args.log)
    if not command:
        run(collector, emitter, args.sample_seconds, args.report_seconds,
            args.directory_seconds, args.disk_free_warning_mib,
            args.memory_available_warning_pct, args.swap_used_warning_pct,
            args.max_samples, sleep=stopped.wait, stopping=stopped.is_set)
        return 128 + forwarded_signal if forwarded_signal else 0

    process = subprocess.Popen(command, start_new_session=True)
    worker = threading.Thread(
        target=run,
        args=(collector, emitter, args.sample_seconds, args.report_seconds,
              args.directory_seconds, args.disk_free_warning_mib,
              args.memory_available_warning_pct, args.swap_used_warning_pct),
        kwargs={"sleep": stopped.wait, "stopping": stopped.is_set},
        name="runner-telemetry", daemon=True,
    )
    worker.start()
    child_status = process.wait()
    stopped.set()
    worker.join(timeout=max(1.0, args.sample_seconds + 1.0))
    if forwarded_signal:
        return 128 + forwarded_signal
    return 128 + (-child_status) if child_status < 0 else child_status


if __name__ == "__main__":
    raise SystemExit(main())
