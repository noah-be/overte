#!/usr/bin/env python3
"""Hermetic tests for macOS frame-timing result validation."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "macos/tools/validate-performance.py"


def percentile(values: list[int], fraction: float) -> int:
    return values[max(0, math.ceil(len(values) * fraction) - 1)]


def valid_payload() -> dict[str, object]:
    samples = [9000 + index * 50 for index in range(120)]
    sorted_samples = sorted(samples)
    return {
        "schema_version": 1,
        "platform": "macos",
        "renderer": "opengl-forward",
        "fixture_entities": 3,
        "duration_ms": 20000,
        "sample_count": len(samples),
        "frame_time_unit": "microseconds",
        "samples_us": samples,
        "mean_frame_ms": sum(samples) / len(samples) / 1000,
        "min_frame_ms": sorted_samples[0] / 1000,
        "p50_frame_ms": percentile(sorted_samples, 0.50) / 1000,
        "p90_frame_ms": percentile(sorted_samples, 0.90) / 1000,
        "p95_frame_ms": percentile(sorted_samples, 0.95) / 1000,
        "p99_frame_ms": percentile(sorted_samples, 0.99) / 1000,
        "max_frame_ms": sorted_samples[-1] / 1000,
        "over_16_67_ms": sum(value > 16667 for value in samples),
        "over_33_33_ms": sum(value > 33333 for value in samples),
        "rates_hz": {
            "render": 60.0,
            "present": 60.0,
            "new_frame": 59.8,
            "dropped": 0.2,
            "simulation": 60.0,
        },
    }


def run(directory: Path, payload: object, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    metrics = directory / "metrics.json"
    result = directory / "result.json"
    junit = directory / "TEST-performance.xml"
    metrics.write_text(json.dumps(payload), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(metrics),
            "--result",
            str(result),
            "--junit",
            str(junit),
            *extra,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    return completed, result, junit


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)

    passed, result_path, junit_path = run(temporary, valid_payload())
    assert passed.returncode == 0, passed.stderr + passed.stdout
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["passed"] is True
    assert result["sample_count"] == 120
    assert abs(result["p95_frame_ms"] - 14.65) < 0.001
    assert result_path.stat().st_mode & 0o777 == 0o600
    assert junit_path.stat().st_mode & 0o777 == 0o600
    junit_root = ET.parse(junit_path).getroot()
    assert junit_root.get("tests") == "1"
    assert junit_root.get("failures") == "0"

    threshold_directory = temporary / "threshold"
    threshold_directory.mkdir()
    threshold, threshold_result, threshold_junit = run(
        threshold_directory, valid_payload(), "--maximum-p95-ms", "10"
    )
    assert threshold.returncode == 1
    assert "exceeds" in threshold_result.read_text(encoding="utf-8")
    assert ET.parse(threshold_junit).getroot().get("failures") == "1"

    mismatch_payload = valid_payload()
    mismatch_payload["p95_frame_ms"] = 1
    mismatch_directory = temporary / "mismatch"
    mismatch_directory.mkdir()
    mismatch, mismatch_result, _ = run(mismatch_directory, mismatch_payload)
    assert mismatch.returncode == 1
    assert "does not match raw samples" in mismatch_result.read_text(encoding="utf-8")

    short_payload = valid_payload()
    short_payload["samples_us"] = short_payload["samples_us"][:5]
    short_payload["sample_count"] = 5
    short_directory = temporary / "short"
    short_directory.mkdir()
    short, short_result, _ = run(short_directory, short_payload)
    assert short.returncode == 1
    assert "below required minimum" in short_result.read_text(encoding="utf-8")

    nonfinite_payload = valid_payload()
    nonfinite_payload["samples_us"][7] = math.nan
    nonfinite_directory = temporary / "nonfinite"
    nonfinite_directory.mkdir()
    nonfinite, nonfinite_result, _ = run(nonfinite_directory, nonfinite_payload)
    assert nonfinite.returncode == 1
    assert "must be finite" in nonfinite_result.read_text(encoding="utf-8")

    malformed_directory = temporary / "malformed"
    malformed_directory.mkdir()
    malformed_metrics = malformed_directory / "metrics.json"
    malformed_metrics.write_text("not-json", encoding="utf-8")
    malformed_result = malformed_directory / "result.json"
    malformed_junit = malformed_directory / "TEST-performance.xml"
    malformed = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(malformed_metrics),
            "--result",
            str(malformed_result),
            "--junit",
            str(malformed_junit),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert malformed.returncode == 1
    assert "could not read" in malformed_result.read_text(encoding="utf-8")
    assert ET.parse(malformed_junit).getroot().get("failures") == "1"

print("macOS performance validator tests passed")
