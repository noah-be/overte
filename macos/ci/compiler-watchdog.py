#!/usr/bin/env python3
"""Run one compiler invocation with live, secret-safe stall diagnostics."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import time
from typing import Any


SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".c++", ".m", ".mm"}
COMPILER_NAMES = {"clang", "clang++", "gcc", "g++", "cc", "c++"}
SECRET_NAME = re.compile(r"(?:token|secret|password|passwd|credential|sign|api.?key|private.?key)", re.I)
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_.-])/(?:[^\s\"'<>|:]+/?)+")


def _cpu_seconds(value: str) -> float:
    day, separator, clock = value.strip().rpartition("-")
    days = int(day) if separator else 0
    fields = clock.split(":")
    if len(fields) == 2:
        fields.insert(0, "0")
    hours, minutes, seconds = fields
    return days * 86400 + int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _snapshot() -> list[dict[str, Any]]:
    result = subprocess.run(
        # Do not request both ``comm`` and ``command`` here.  On macOS/BSD ps,
        # the former may be truncated to a single character when the process
        # has an unusual argv layout.  ``args`` is the final, unlimited-width
        # column and is sufficient to derive the real compiler executable.
        ["ps", "-ww", "-axo", "pid=,ppid=,time=,rss=,%cpu=,args="],
        check=True, capture_output=True, text=True,
    )
    rows = _parse_snapshot(result.stdout)
    if sys.platform.startswith("linux"):
        # GNU ps rounds short-lived CPU time too coarsely for the hermetic
        # watchdog tests and Linux self-hosted runners.  /proc exposes the
        # cumulative user/system ticks without relying on averaged %CPU.
        try:
            ticks_per_second = os.sysconf("SC_CLK_TCK")
        except (OSError, ValueError):
            ticks_per_second = 0
        if ticks_per_second:
            for row in rows:
                try:
                    stat_fields = Path(f"/proc/{row['pid']}/stat").read_text().rsplit(
                        ")", 1
                    )[1].split()
                    row["cpu"] = (
                        int(stat_fields[11]) + int(stat_fields[12])
                    ) / ticks_per_second
                except (OSError, ValueError, IndexError):
                    pass
    return rows


def _parse_snapshot(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = line.strip().split(None, 5)
        if len(fields) != 6:
            continue
        try:
            command = fields[5]
            try:
                argv = shlex.split(command)
            except ValueError:
                argv = command.split(None, 1)
            executable = os.path.basename(argv[0]) if argv else ""
            rows.append({
                "pid": int(fields[0]), "ppid": int(fields[1]),
                "cpu": _cpu_seconds(fields[2]), "rss": int(fields[3]),
                "cpu_pct": float(fields[4]),
                "comm": executable, "command": command,
            })
        except ValueError:
            continue
    return rows


def _tree(rows: list[dict[str, Any]], root: int) -> list[dict[str, Any]]:
    selected = {root}
    changed = True
    while changed:
        changed = False
        for row in rows:
            if int(row["ppid"]) in selected and int(row["pid"]) not in selected:
                selected.add(int(row["pid"]))
                changed = True
    return [row for row in rows if int(row["pid"]) in selected]


def _expanded_arguments(arguments: list[str], depth: int = 0) -> list[str]:
    """Expand compiler response files for private, exact process correlation."""
    if depth >= 3:
        return arguments
    expanded: list[str] = []
    for value in arguments:
        if not value.startswith("@") or len(value) == 1:
            expanded.append(value)
            continue
        try:
            contents = Path(value[1:]).read_text(encoding="utf-8")
            response = shlex.split(contents)
        except (OSError, UnicodeError, ValueError):
            expanded.append(value)
        else:
            expanded.extend(_expanded_arguments(response, depth + 1))
    return expanded


def _compiler_markers(arguments: list[str]) -> tuple[str | None, str | None]:
    arguments = _expanded_arguments(arguments)
    source = next((value for value in reversed(arguments)
                   if Path(value).suffix.lower() in SOURCE_SUFFIXES), None)
    output = None
    for index, value in enumerate(arguments):
        if value == "-o" and index + 1 < len(arguments):
            output = arguments[index + 1]
        elif value.startswith("-o") and len(value) > 2:
            output = value[2:]
    return source, output


def _same_argument(candidate: str, marker: str) -> bool:
    if candidate == marker:
        return True
    try:
        return Path(candidate).resolve(strict=False) == Path(marker).resolve(strict=False)
    except (OSError, RuntimeError):
        return False


def _correlated_compilers(rows: list[dict[str, Any]], source: str | None,
                          output: str | None) -> list[dict[str, Any]]:
    if not source or not output:
        return []
    matches = []
    for row in rows:
        try:
            argv = shlex.split(str(row.get("command", "")))
        except ValueError:
            continue
        if not argv or os.path.basename(argv[0]).lower() not in COMPILER_NAMES:
            continue
        candidate_source, candidate_output = _compiler_markers(argv[1:])
        if (candidate_source is not None and candidate_output is not None
                and _same_argument(candidate_source, source)
                and _same_argument(candidate_output, output)):
            matches.append(row)
    return matches


def _language(compiler: str, arguments: list[str]) -> str:
    suffixes = {Path(value).suffix.lower() for value in arguments if not value.startswith("-")}
    if ".mm" in suffixes:
        return "objcxx"
    if ".m" in suffixes:
        return "objc"
    if suffixes & {".cc", ".cpp", ".cxx", ".c++"} or "++" in Path(compiler).name:
        return "cxx"
    return "c"


def _emit(kind: str, invocation: str, elapsed: float, **fields: object) -> None:
    record = {
        "compiler_watchdog": kind,
        "id": invocation,
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "elapsed_s": round(elapsed, 1),
    }
    record.update(fields)
    line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    live_log = os.environ.get("OVERTE_COMPILER_WATCHDOG_LOG")
    if live_log:
        descriptor = os.open(live_log, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, line.encode("utf-8"))
        finally:
            os.close(descriptor)
    else:
        sys.stdout.write(line)
        sys.stdout.flush()


def _output_signature(output: str | None) -> tuple[int, int] | None:
    if not output:
        return None
    try:
        stat = Path(output).stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _sanitize_sample(text: str) -> str:
    for name, value in os.environ.items():
        if value and len(value) >= 4 and SECRET_NAME.search(name):
            text = text.replace(value, "<redacted-secret>")
    text = re.sub(r"(?i)(token|secret|password|credential|api.?key)(\s*[:=]\s*)\S+",
                  r"\1\2<redacted-secret>", text)
    return ABSOLUTE_PATH.sub("<redacted-path>", text)


def _write_private(path: Path, contents: str) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, contents.encode("utf-8", "replace"))
    finally:
        os.close(descriptor)


def _collect_diagnostics(invocation: str, source_label: str,
                         active: list[dict[str, Any]], correlated: list[dict[str, Any]]) -> None:
    root = os.environ.get("OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS")
    if not root:
        return
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    safe_rows = [{key: row[key] for key in ("pid", "ppid", "cpu", "cpu_pct", "rss", "comm")
                  if key in row}
                 for row in active]
    report = {"id": invocation, "source": source_label, "processes": safe_rows}
    _write_private(directory / f"stall-{invocation}.json",
                   json.dumps(report, indent=2, sort_keys=True) + "\n")
    sample = shutil.which("sample")
    targets = correlated or [row for row in active if str(row["comm"]).lower() in COMPILER_NAMES]
    if not sample or not targets:
        return
    for row in targets:
        pid = int(row["pid"])
        try:
            result = subprocess.run([sample, str(pid), "3", "1"], capture_output=True,
                                    text=True, timeout=15, check=False)
            contents = result.stdout + result.stderr
        except (OSError, subprocess.TimeoutExpired) as error:
            contents = f"sample unavailable: {type(error).__name__}\n"
        _write_private(directory / f"sample-{invocation}-{pid}.txt", _sanitize_sample(contents))


def _signal_pids(pids: set[int], signum: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, signum)
        except (ProcessLookupError, PermissionError):
            pass


def _signal_group(pid: int, signum: int) -> None:
    try:
        os.killpg(pid, signum)
    except (ProcessLookupError, PermissionError):
        pass


def _terminate(process: subprocess.Popen[bytes], extra_pids: set[int], grace: float) -> None:
    _signal_group(process.pid, signal.SIGTERM)
    _signal_pids(extra_pids, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.05)
    # The group can outlive its leader, so always address it after the grace
    # period rather than conditioning cleanup on the leader's status.
    _signal_group(process.pid, signal.SIGKILL)
    _signal_pids(extra_pids, signal.SIGKILL)


def run(command: list[str], interval: float, inactivity_timeout: float, grace: float) -> int:
    compiler, arguments = command[0], command[1:]
    invocation = secrets.token_hex(6)
    language = _language(compiler, arguments)
    source_marker, output_marker = _compiler_markers(arguments)
    source_label = Path(source_marker).name if source_marker else "unknown"
    executable = [compiler, *arguments]
    cache = shutil.which("sccache")
    if cache and os.environ.get("OVERTE_COMPILER_WATCHDOG_DISABLE_SCCACHE") != "1":
        executable.insert(0, cache)

    started = time.monotonic()
    process: subprocess.Popen[bytes] = subprocess.Popen(executable, start_new_session=True)
    _emit("start", invocation, 0, language=language, source=source_label, pid=process.pid)
    last_cpu = -1.0
    last_output = _output_signature(output_marker)
    last_progress = started
    correlated_pids: set[int] = set()
    forwarded_signal = 0
    forwarded_at = 0.0

    def forward(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal, forwarded_at
        if not forwarded_signal:
            forwarded_signal = signum
            forwarded_at = time.monotonic()
        _signal_group(process.pid, signum)
        _signal_pids(correlated_pids, signum)

    old_term = signal.signal(signal.SIGTERM, forward)
    old_int = signal.signal(signal.SIGINT, forward)
    try:
        while True:
            status = process.poll()
            if status is not None and not forwarded_signal:
                break
            if forwarded_signal and time.monotonic() >= forwarded_at + grace:
                # A compiler leader may already have exited while an ignoring
                # grandchild still owns the session. Kill the group regardless.
                _signal_group(process.pid, signal.SIGKILL)
                _signal_pids(correlated_pids, signal.SIGKILL)
                break
            wait_for = interval
            if forwarded_signal:
                wait_for = min(wait_for, max(0.01, forwarded_at + grace - time.monotonic()))
            if status is None:
                try:
                    process.wait(timeout=wait_for)
                except subprocess.TimeoutExpired:
                    pass
            else:
                time.sleep(wait_for)
            try:
                rows = _snapshot()
                # The process can finish while a comparatively expensive macOS
                # process-table snapshot is being collected. Never classify an
                # invocation that has already exited as stalled.
                if process.poll() is not None and not forwarded_signal:
                    continue
                tree = _tree(rows, process.pid)
                correlated = _correlated_compilers(rows, source_marker, output_marker)
                correlated_pids = {int(row["pid"]) for row in correlated}
                active_by_pid = {int(row["pid"]): row for row in [*tree, *correlated]}
                active = list(active_by_pid.values())
                if forwarded_signal:
                    # A daemon-owned compiler is outside the launcher's process
                    # group. Forward again after correlation discovers it.
                    _signal_pids(correlated_pids, forwarded_signal)
                cpu = sum(float(row["cpu"]) for row in active)
                cpu_pct = sum(float(row.get("cpu_pct", 0.0)) for row in active)
                rss = sum(int(row["rss"]) for row in active) / 1024.0
                output_signature = _output_signature(output_marker)
                # Cumulative CPU time must advance; an averaged ``%cpu`` value
                # can remain non-zero after a process has stopped doing work
                # and must therefore never keep a genuinely stalled compiler
                # alive indefinitely.
                if (cpu > last_cpu
                        or (output_signature is not None and output_signature != last_output)):
                    last_cpu = cpu
                    last_output = output_signature
                    last_progress = time.monotonic()
                idle = time.monotonic() - last_progress
                _emit("progress", invocation, time.monotonic() - started,
                      language=language, source=source_label, processes=len(active),
                      cpu_s=round(cpu, 1), cpu_pct=round(cpu_pct, 1),
                      rss_mib=round(rss, 1), inactive_s=round(idle, 1))
                if idle >= inactivity_timeout:
                    _collect_diagnostics(invocation, source_label, active, correlated)
                    _emit("stalled", invocation, time.monotonic() - started,
                          language=language, source=source_label, inactive_s=round(idle, 1))
                    _terminate(process, correlated_pids, grace)
                    process.wait()
                    _emit("end", invocation, time.monotonic() - started,
                          language=language, source=source_label, exit_code=124,
                          reason="inactivity")
                    return 124
            except Exception as error:
                _emit("monitor_error", invocation, time.monotonic() - started,
                      language=language, source=source_label,
                      error=type(error).__name__)
        status = process.wait()
        if forwarded_signal:
            result = 128 + forwarded_signal
        elif status < 0:
            result = 128 - status
        else:
            result = status
        _emit("end", invocation, time.monotonic() - started, language=language,
              source=source_label, exit_code=result)
        return result
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def _parse_cli(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float,
                        default=float(os.environ.get("OVERTE_COMPILER_WATCHDOG_INTERVAL", "30")))
    parser.add_argument("--inactivity-timeout", type=float,
                        default=float(os.environ.get("OVERTE_COMPILER_STALL_TIMEOUT", "600")))
    parser.add_argument("--term-grace", type=float, default=10.0)
    # CMake may split ``CC="watchdog -- clang"`` into CMAKE_C_COMPILER and
    # CMAKE_C_COMPILER_ARG1, then place probe flags before ARG1.  This produces
    # ``watchdog -E -isysroot <sdk> -- clang``.  Parse our known options only
    # before the separator and preserve every other token as a compiler
    # argument after the compiler executable.  Normal launcher invocations
    # remain ``watchdog -- clang <args>``.
    if "--" in argv:
        separator = argv.index("--")
        args, compiler_arguments = parser.parse_known_args(argv[:separator])
        command_tail = argv[separator + 1:]
        command = ([command_tail[0], *compiler_arguments, *command_tail[1:]]
                   if command_tail else [])
    else:
        # Some dependency projects invoke CMAKE_C_COMPILER directly for
        # preprocessing and omit CMAKE_C_COMPILER_ARG1 entirely.  In that
        # specific CMake form the wrapper receives only compiler arguments.
        # Require an explicitly provisioned real compiler rather than guessing
        # from PATH, then forward the complete argument vector unchanged.
        fallback = os.environ.get("OVERTE_COMPILER_WATCHDOG_FALLBACK_COMPILER", "")
        args, compiler_arguments = parser.parse_known_args(argv)
        command = [fallback, *compiler_arguments] if fallback else []
    if not command or args.interval <= 0 or args.inactivity_timeout <= 0 or args.term_grace < 0:
        parser.error("a compiler command (or explicit fallback) and positive timing values are required")
    return args, command


def main() -> int:
    args, command = _parse_cli(sys.argv[1:])
    return run(command, args.interval, args.inactivity_timeout, args.term_grace)


if __name__ == "__main__":
    raise SystemExit(main())
