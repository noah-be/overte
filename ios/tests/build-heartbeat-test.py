#!/usr/bin/env python3
"""Tests for the secret-safe long-build heartbeat."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
HEARTBEAT = ROOT / "ios" / "ci" / "build-heartbeat.py"
SPEC = importlib.util.spec_from_file_location("build_heartbeat", HEARTBEAT)
assert SPEC and SPEC.loader
heartbeat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(heartbeat)


def test_cpu_time() -> None:
    assert heartbeat.parse_cpu_time("01:02") == 62
    assert heartbeat.parse_cpu_time("01:02:03") == 3723
    assert heartbeat.parse_cpu_time("2-01:02:03") == 176523


def test_process_tree_and_metrics() -> None:
    processes = heartbeat.parse_processes(
        [
            "100 1 00:10 1024 bash",
            "101 100 01:00 2048 /usr/bin/xcodebuild",
            "102 101 00:02 512 clang++",
            "103 102 00:01 256 sccache",
            "200 1 09:00 9999 clang",
        ]
    )
    metrics = heartbeat.process_metrics(processes, 100)
    assert metrics == {
        "build_alive": True,
        "descendants": 3,
        "xcodebuild": 1,
        "clang": 1,
        "sccache": 1,
        "active_cpu_s": 73.0,
        "rss_mib": 3.75,
    }


def test_log_metrics() -> None:
    with tempfile.TemporaryDirectory() as directory:
        log = Path(directory) / "xcode-build.log"
        assert heartbeat.log_metrics(log, time.time()) == {
            "log_bytes": 0,
            "log_mtime_utc": None,
            "log_stale_s": None,
        }
        log.write_text("build output\n", encoding="utf-8")
        metrics = heartbeat.log_metrics(log, time.time())
        assert metrics["log_bytes"] == 13
        assert str(metrics["log_mtime_utc"]).endswith("Z")
        assert 0 <= int(metrics["log_stale_s"]) <= 2


def test_secret_safe_short_lifecycle() -> None:
    secret = "SIGNING_TOKEN_DO_NOT_PRINT_719"
    with tempfile.TemporaryDirectory() as directory:
        log = Path(directory) / "xcode-build.log"
        build = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.2)", secret],
            env={"PATH": str(Path(sys.executable).parent), "SECRET_CANARY": secret},
        )
        monitor = subprocess.Popen(
            [
                sys.executable,
                str(HEARTBEAT),
                "--root-pid",
                str(build.pid),
                "--log",
                str(log),
                "--interval",
                "0.05",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        build.wait(timeout=3)
        output, errors = monitor.communicate(timeout=3)
        assert monitor.returncode == 0, errors
        assert secret not in output
        records = [json.loads(line) for line in output.splitlines()]
        assert records
        assert records[0]["build_alive"] is True
        assert records[-1]["build_alive"] is False
        for field in (
            "utc",
            "elapsed_s",
            "descendants",
            "xcodebuild",
            "clang",
            "sccache",
            "active_cpu_s",
            "rss_mib",
            "log_bytes",
            "log_mtime_utc",
            "log_stale_s",
        ):
            assert field in records[0]


def main() -> None:
    test_cpu_time()
    test_process_tree_and_metrics()
    test_log_metrics()
    test_secret_safe_short_lifecycle()
    print("Build heartbeat tests passed")


if __name__ == "__main__":
    main()
