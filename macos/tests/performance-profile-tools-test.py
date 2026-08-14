#!/usr/bin/env python3
"""Hermetic contracts for profile generation and matrix aggregation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "macos/tools/render-performance-profile.py"
ANALYZER = ROOT / "macos/tools/analyze-performance-matrix.py"
PROFILES = ROOT / "macos/tests/performance-profiles.json"
TEMPLATE = ROOT / "macos/tests/profile-performance-smoke.js"


def run_result(profile: str, index: int, present: float, p95: float, renderer: str) -> dict[str, object]:
    samples = [int(p95 * 1000)] * 100
    distribution = {"count": 8, "mean": present, "min": present, "p10": present,
                    "p50": present, "p95": present, "max": present}
    return {
        "schema_version": 2,
        "platform": "macos",
        "fixture_version": "lit-grid-v1",
        "profile_id": profile,
        "run_index": index,
        "quality_score": 35 if profile == "forward-compat" else 85,
        "requested_profile": {"id": profile},
        "platform_info": {
            "computer": {"model": "Mac"},
            "cpu": {"model": "CPU"},
            "gpu": {"model": renderer},
            "display": {"width": 1380},
        },
        "sample_count": len(samples),
        "samples_us": samples,
        "p95_frame_ms": p95,
        "rates_hz": {
            "render": distribution,
            "present": distribution,
            "new_frame": distribution,
            "dropped": {**distribution, "p50": 0},
            "simulation": distribution,
        },
    }


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    generated = temporary / "generated.js"
    generation = subprocess.run(
        [sys.executable, str(GENERATOR), "--profiles", str(PROFILES), "--profile", "forward-compat",
         "--template", str(TEMPLATE), "--output", str(generated), "--trace", str(temporary / "trace.gz"),
         "--run-index", "2"],
        text=True, capture_output=True, check=False,
    )
    assert generation.returncode == 0, generation.stderr
    source = generated.read_text(encoding="utf-8")
    assert source.startswith("var OVERTE_MACOS_PERFORMANCE_CASE = ")
    assert '"id": "forward-compat"' in source
    assert generated.stat().st_mode & 0o777 == 0o600

    rejected = subprocess.run(
        [sys.executable, str(GENERATOR), "--profiles", str(PROFILES), "--profile", "../escape",
         "--template", str(TEMPLATE), "--output", str(temporary / "bad.js"),
         "--trace", str(temporary / "trace.gz"), "--run-index", "1"],
        text=True, capture_output=True, check=False,
    )
    assert rejected.returncode != 0

    matrix = temporary / "matrix"
    for profile, present, p95 in (("forward-compat", 60.0, 12.0), ("deferred-balanced", 55.0, 16.0)):
        for index in range(1, 4):
            directory = matrix / profile / f"run-{index}"
            directory.mkdir(parents=True)
            payload = run_result(profile, index, present, p95, "Apple M4")
            (directory / "macos-profile.json").write_text(json.dumps(payload), encoding="utf-8")
    result = temporary / "result.json"
    junit = temporary / "junit.xml"
    analysis = subprocess.run(
        [sys.executable, str(ANALYZER), str(matrix), "--result", str(result),
         "--junit", str(junit), "--minimum-runs", "3"],
        text=True, capture_output=True, check=False,
    )
    assert analysis.returncode == 0, analysis.stderr + analysis.stdout
    summary = json.loads(result.read_text(encoding="utf-8"))
    assert summary["diagnostic_only"] is False
    assert summary["selected_profile"] == "forward-compat"
    assert result.stat().st_mode & 0o777 == 0o600

    software = temporary / "software"
    for profile, present, p95 in (("forward-compat", 1.0, 8.0), ("deferred-balanced", 0.75, 10.0)):
        directory = software / profile / "run-1"
        directory.mkdir(parents=True)
        (directory / "macos-profile.json").write_text(
            json.dumps(run_result(profile, 1, present, p95, "Apple Software Renderer")), encoding="utf-8"
        )
    software_result = temporary / "software.json"
    software_junit = temporary / "software.xml"
    software_analysis = subprocess.run(
        [sys.executable, str(ANALYZER), str(software), "--result", str(software_result),
         "--junit", str(software_junit), "--minimum-runs", "1"],
        text=True, capture_output=True, check=False,
    )
    assert software_analysis.returncode == 0, software_analysis.stderr + software_analysis.stdout
    software_summary = json.loads(software_result.read_text(encoding="utf-8"))
    assert software_summary["diagnostic_only"] is True
    assert software_summary["selected_profile"] == "deferred-balanced"

print("macOS performance profile tool tests passed")
