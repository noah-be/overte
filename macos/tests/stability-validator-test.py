#!/usr/bin/env python3
"""Hermetic tests for macOS repeated-runtime stability reporting."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "macos/tools/validate-stability.py"
MARKERS = (
    "OVERTE_MACOS_ENTITY_GATE serverless_import_committed",
    "OVERTE_MACOS_ENTITY_GATE entity_tree_nonempty",
    "OVERTE_MACOS_ENTITY_GATE render_handoff",
    "OVERTE_MACOS_SMOKE passed",
)


def write_run(root: Path, index: int, *, exit_code: int = 0, screenshot: bool = True) -> None:
    directory = root / f"run-{index:02d}"
    directory.mkdir(parents=True)
    (directory / "serverless-process.json").write_text(
        json.dumps(
            {
                "elapsed_seconds": 12.5 + index,
                "exit_code": exit_code,
                "timed_out": False,
                "sent_sigterm": False,
                "sent_sigkill": False,
            }
        ),
        encoding="utf-8",
    )
    (directory / "serverless-screenshot.json").write_text(
        json.dumps({"passed": screenshot}), encoding="utf-8"
    )
    (directory / "serverless.log").write_text("\n".join(MARKERS) + "\n", encoding="utf-8")


def run(root: Path, iterations: int) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    result = root / "summary.json"
    junit = root / "TEST-stability.xml"
    completed = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(root),
            "--iterations",
            str(iterations),
            "--result",
            str(result),
            "--junit",
            str(junit),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    return completed, result, junit


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    passing = temporary / "passing"
    passing.mkdir()
    for index in range(1, 4):
        write_run(passing, index)
    completed, result_path, junit_path = run(passing, 3)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["passed"] is True
    assert result["passed_iterations"] == 3
    assert result["failed_iterations"] == 0
    assert result_path.stat().st_mode & 0o777 == 0o600
    assert junit_path.stat().st_mode & 0o777 == 0o600
    junit = ET.parse(junit_path).getroot()
    assert junit.get("tests") == "3"
    assert junit.get("failures") == "0"

    failing = temporary / "failing"
    failing.mkdir()
    write_run(failing, 1)
    write_run(failing, 2, exit_code=139)
    write_run(failing, 3, screenshot=False)
    failed, failed_result_path, failed_junit_path = run(failing, 3)
    assert failed.returncode == 1
    failed_result = json.loads(failed_result_path.read_text(encoding="utf-8"))
    assert failed_result["passed"] is False
    assert failed_result["failed_iterations"] == 2
    assert ET.parse(failed_junit_path).getroot().get("failures") == "2"

    incomplete = temporary / "incomplete"
    incomplete.mkdir()
    write_run(incomplete, 1)
    missing, missing_result_path, _ = run(incomplete, 2)
    assert missing.returncode == 1
    missing_result = json.loads(missing_result_path.read_text(encoding="utf-8"))
    assert missing_result["failed_iterations"] == 1
    assert "missing or invalid" in " ".join(missing_result["runs"][1]["failures"])

print("macOS stability validator tests passed")
