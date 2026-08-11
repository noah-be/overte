#!/usr/bin/env python3
"""Hermetic tests for macOS build progress and checkpoint metadata."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "macos/tools/run-build-with-progress.py"

with tempfile.TemporaryDirectory() as temporary:
    output = Path(temporary)
    child = (
        "import time; "
        "print('[  5%] Building CXX object', flush=True); "
        "time.sleep(0.08); "
        "print('[ 99%] Linking CXX executable Overte', flush=True); "
        "time.sleep(0.08); "
        "print('Running macdeployqt and deploy-conan-dylibs', flush=True); "
        "print('[100%] Built target Overte', flush=True)"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(MONITOR),
            "--heartbeat-seconds",
            "0.05",
            "--log",
            str(output / "build.log"),
            "--result",
            str(output / "build.json"),
            "--",
            sys.executable,
            "-c",
            child,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        env={**os.environ, "GITHUB_ACTIONS": "true"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    for phase in ("compile", "link", "bundle", "complete"):
        assert f"phase={phase}" in completed.stdout
    assert "::notice title=macOS build progress::" in completed.stdout
    metadata = json.loads((output / "build.json").read_text(encoding="utf-8"))
    assert metadata["exit_code"] == 0
    assert metadata["max_progress"] == 100
    assert metadata["final_phase"] == "bundle"
    assert "Built target Overte" in (output / "build.log").read_text(encoding="utf-8")

    failed = subprocess.run(
        [
            sys.executable,
            str(MONITOR),
            "--log",
            str(output / "failed.log"),
            "--result",
            str(output / "failed.json"),
            "--",
            sys.executable,
            "-c",
            "print('[ 30%] Building CXX object', flush=True); raise SystemExit(7)",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert failed.returncode == 7
    assert "phase=failed" in failed.stdout
    assert json.loads((output / "failed.json").read_text(encoding="utf-8"))["exit_code"] == 7

print("macOS build progress contract valid")
