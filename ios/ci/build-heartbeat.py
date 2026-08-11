#!/usr/bin/env python3
"""Emit secret-safe liveness metrics for a long-running build process tree."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Iterable


def parse_cpu_time(value: str) -> float:
    """Convert ps TIME values ([[dd-]hh:]mm:ss) to seconds."""
    day_parts = value.strip().split("-", 1)
    days = int(day_parts[0]) if len(day_parts) == 2 else 0
    fields = day_parts[-1].split(":")
    if len(fields) == 3:
        hours, minutes, seconds = fields
    elif len(fields) == 2:
        hours = "0"
        minutes, seconds = fields
    else:
        raise ValueError("unsupported ps CPU time")
    return days * 86400 + int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_processes(lines: Iterable[str]) -> list[dict[str, object]]:
    processes: list[dict[str, object]] = []
    for line in lines:
        fields = line.strip().split(None, 4)
        if len(fields) != 5:
            continue
        pid, ppid, cpu_time, rss_kib, command = fields
        try:
            processes.append(
                {
                    "pid": int(pid),
                    "ppid": int(ppid),
                    "cpu_s": parse_cpu_time(cpu_time),
                    "rss_kib": int(rss_kib),
                    "command": os.path.basename(command),
                }
            )
        except ValueError:
            continue
    return processes


def process_tree(processes: Iterable[dict[str, object]], root_pid: int) -> list[dict[str, object]]:
    process_list = list(processes)
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for process in process_list:
            if int(process["ppid"]) in selected and int(process["pid"]) not in selected:
                selected.add(int(process["pid"]))
                changed = True
    return [process for process in process_list if int(process["pid"]) in selected]


def read_processes() -> list[dict[str, object]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,time=,rss=,comm="],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_processes(result.stdout.splitlines())


def process_metrics(processes: Iterable[dict[str, object]], root_pid: int) -> dict[str, object]:
    tree = process_tree(processes, root_pid)
    commands = [str(process["command"]).lower() for process in tree]
    return {
        "build_alive": any(int(process["pid"]) == root_pid for process in tree),
        "descendants": max(0, len(tree) - 1),
        "xcodebuild": sum(command == "xcodebuild" for command in commands),
        "clang": sum(command in {"clang", "clang++"} for command in commands),
        "sccache": sum(command == "sccache" for command in commands),
        "active_cpu_s": round(sum(float(process["cpu_s"]) for process in tree), 3),
        "rss_mib": round(sum(int(process["rss_kib"]) for process in tree) / 1024.0, 3),
    }


def log_metrics(path: Path, now: float) -> dict[str, object]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"log_bytes": 0, "log_mtime_utc": None, "log_stale_s": None}
    except OSError:
        return {
            "log_bytes": 0,
            "log_mtime_utc": None,
            "log_stale_s": None,
            "log_error": "log_stat_failed",
        }
    modified = dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc)
    return {
        "log_bytes": stat.st_size,
        "log_mtime_utc": modified.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "log_stale_s": max(0, int(now - stat.st_mtime)),
    }


def emit_heartbeats(root_pid: int, log_path: Path, interval: float) -> int:
    started = time.monotonic()
    while True:
        now = time.time()
        record: dict[str, object] = {
            "heartbeat": "build",
            "utc": dt.datetime.fromtimestamp(now, dt.timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "elapsed_s": int(time.monotonic() - started),
        }
        try:
            record.update(process_metrics(read_processes(), root_pid))
        except Exception:  # Monitoring must never affect the build it observes.
            record.update(
                {
                    "build_alive": True,
                    "descendants": None,
                    "xcodebuild": None,
                    "clang": None,
                    "sccache": None,
                    "active_cpu_s": None,
                    "rss_mib": None,
                    "monitor_error": "process_snapshot_failed",
                }
            )
        record.update(log_metrics(log_path, now))
        print(json.dumps(record, separators=(",", ":"), sort_keys=True), flush=True)
        if record["build_alive"] is False:
            return 0
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-pid", type=int, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=30.0)
    args = parser.parse_args()
    if args.root_pid < 1:
        parser.error("--root-pid must be positive")
    if args.interval <= 0:
        parser.error("--interval must be positive")
    return emit_heartbeats(args.root_pid, args.log, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
