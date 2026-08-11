#!/usr/bin/env python3
"""Run one compiler invocation with secret-safe progress and stall detection."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


def _cpu_seconds(value: str) -> float:
    day, _, clock = value.strip().rpartition("-")
    days = int(day) if day else 0
    fields = clock.split(":")
    if len(fields) == 2:
        fields.insert(0, "0")
    hours, minutes, seconds = fields
    return days * 86400 + int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _snapshot() -> list[dict[str, object]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,time=,rss=,comm=,command="],
        check=True, capture_output=True, text=True,
    )
    rows: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 5)
        if len(fields) != 6:
            continue
        try:
            rows.append({"pid": int(fields[0]), "ppid": int(fields[1]),
                         "cpu": _cpu_seconds(fields[2]), "rss": int(fields[3]),
                         "comm": os.path.basename(fields[4]), "command": fields[5]})
        except ValueError:
            continue
    return rows


def _tree(rows: list[dict[str, object]], root: int) -> list[dict[str, object]]:
    selected = {root}
    changed = True
    while changed:
        changed = False
        for row in rows:
            if int(row["ppid"]) in selected and int(row["pid"]) not in selected:
                selected.add(int(row["pid"]))
                changed = True
    return [row for row in rows if int(row["pid"]) in selected]


def _compiler_markers(arguments: list[str]) -> tuple[str | None, str | None]:
    source = next((value for value in reversed(arguments)
                   if Path(value).suffix.lower() in {".c", ".cc", ".cpp", ".cxx", ".c++", ".m", ".mm"}), None)
    output = None
    for index, value in enumerate(arguments[:-1]):
        if value == "-o":
            output = arguments[index + 1]
    return source, output


def _correlated_compilers(rows: list[dict[str, object]], source: str | None,
                          output: str | None) -> list[dict[str, object]]:
    if not source or not output:
        return []
    return [row for row in rows
            if str(row["comm"]).lower() in {"clang", "clang++"}
            and source in str(row.get("command", ""))
            and output in str(row.get("command", ""))]


def _emit(kind: str, invocation: str, elapsed: float, **fields: object) -> None:
    record = {
        "compiler_watchdog": kind,
        "id": invocation,
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "elapsed_s": round(elapsed, 1),
    }
    record.update(fields)
    line = json.dumps(record, separators=(",", ":"), sort_keys=True)
    live_log = os.environ.get("OVERTE_COMPILER_WATCHDOG_LOG")
    if live_log:
        descriptor = os.open(live_log, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, (line + "\n").encode("utf-8"))
        finally:
            os.close(descriptor)
    else:
        print(line, flush=True)


def _language(compiler: str, arguments: list[str]) -> str:
    suffixes = {Path(value).suffix.lower() for value in arguments if not value.startswith("-")}
    if ".mm" in suffixes:
        return "objcxx"
    if ".m" in suffixes:
        return "objc"
    if suffixes & {".cc", ".cpp", ".cxx", ".c++"} or "++" in Path(compiler).name:
        return "cxx"
    return "c"


def _terminate_group(pid: int, grace: float) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(command: list[str], interval: float, inactivity_timeout: float, grace: float) -> int:
    compiler, arguments = command[0], command[1:]
    identity = hashlib.sha256("\0".join(command).encode("utf-8", "surrogateescape")).hexdigest()[:12]
    language = _language(compiler, arguments)
    source_marker, output_marker = _compiler_markers(arguments)
    source_label = Path(source_marker).name if source_marker else "unknown"
    executable = [compiler, *arguments]
    cache = shutil.which("sccache")
    if cache and os.environ.get("OVERTE_COMPILER_WATCHDOG_DISABLE_SCCACHE") != "1":
        executable.insert(0, cache)

    started = time.monotonic()
    process = subprocess.Popen(executable, start_new_session=True)
    _emit("start", identity, 0, language=language, source=source_label, pid=process.pid)
    last_cpu = -1.0
    last_progress = started

    def forward(signum: int, _frame: object) -> None:
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass

    old_term = signal.signal(signal.SIGTERM, forward)
    old_int = signal.signal(signal.SIGINT, forward)
    try:
        while process.poll() is None:
            time.sleep(interval)
            try:
                rows = _snapshot()
                active_by_pid = {int(row["pid"]): row for row in _tree(rows, process.pid)}
                # sccache may own clang from its daemon. Correlate the exact
                # source/output pair internally without ever logging arguments.
                for row in _correlated_compilers(rows, source_marker, output_marker):
                    active_by_pid[int(row["pid"])] = row
                active = list(active_by_pid.values())
                cpu = sum(float(row["cpu"]) for row in active)
                rss = sum(int(row["rss"]) for row in active) / 1024.0
                if cpu > last_cpu:
                    last_cpu = cpu
                    last_progress = time.monotonic()
                idle = time.monotonic() - last_progress
                _emit("progress", identity, time.monotonic() - started, language=language,
                      source=source_label,
                      processes=len(active), cpu_s=round(cpu, 1), rss_mib=round(rss, 1),
                      inactive_s=round(idle, 1))
                if idle >= inactivity_timeout:
                    _emit("stalled", identity, time.monotonic() - started,
                          language=language, source=source_label, inactive_s=round(idle, 1))
                    _terminate_group(process.pid, grace)
                    process.wait()
                    return 124
            except Exception:
                _emit("monitor_error", identity, time.monotonic() - started,
                      language=language, source=source_label)
        status = process.wait()
        _emit("end", identity, time.monotonic() - started, language=language,
              source=source_label, exit_code=status)
        return status
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float,
                        default=float(os.environ.get("OVERTE_COMPILER_WATCHDOG_INTERVAL", "30")))
    parser.add_argument("--inactivity-timeout", type=float,
                        default=float(os.environ.get("OVERTE_COMPILER_STALL_TIMEOUT", "600")))
    parser.add_argument("--term-grace", type=float, default=10.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.interval <= 0 or args.inactivity_timeout <= 0 or args.term_grace < 0:
        parser.error("a compiler command and positive timing values are required")
    return run(command, args.interval, args.inactivity_timeout, args.term_grace)


if __name__ == "__main__":
    raise SystemExit(main())
