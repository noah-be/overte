#!/usr/bin/env python3
"""Hermetic contracts for profile generation and fail-closed matrix selection."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "macos/tools/render-performance-profile.py"
ANALYZER = ROOT / "macos/tools/analyze-performance-matrix.py"
PROFILES = ROOT / "macos/tests/performance-profiles.json"
TEMPLATE = ROOT / "macos/tests/profile-performance-smoke.js"
CATALOG = json.loads(PROFILES.read_text(encoding="utf-8"))
PROFILE_BY_ID = {profile["id"]: profile for profile in CATALOG["profiles"]}
PROFILE_FIELDS = (
    "render_method", "shadows", "haze", "bloom", "ambient_occlusion", "local_lighting",
    "procedural_materials", "antialiasing", "viewport_scale", "forward_samples",
)


def distribution(value: float) -> dict[str, float | int]:
    return {"count": 120, "mean": value, "min": value, "p10": value,
            "p50": value, "p95": value, "max": value}


def run_result(profile_id: str, index: int, present: float, p95: float,
               renderer: str, fixture_mode: str) -> dict[str, object]:
    profile = PROFILE_BY_ID[profile_id]
    samples = [int(p95 * 1000)] * 120
    software = "software" in renderer.lower()
    lod_values = {
        "present_ms": 500.0 if software else 16.0,
        "engine_ms": 4.0,
        "batch_ms": 450.0 if software else 8.0,
        "gpu_ms": 450.0 if software else 8.0,
    }
    lod_rows = [
        {"elapsed_ms": offset * 250, **lod_values}
        for offset in range(1, 4)
    ]
    lod_timings = {
        "sampling_interval_ms": 250,
        "semantics": "polled_latest_and_moving_averages",
        "raw_samples": lod_rows,
    }
    for name, value in lod_values.items():
        lod_timings[name] = {
            **distribution(value),
            "count": 3,
            "available": True,
            "invalid_count": 0,
            "zero_count": int(value == 0) * 3,
            "positive_count": int(value > 0) * 3,
        }
    stats = {
        name: distribution(value)
        for name, value in {
            "gpuFrameTime": lod_values["gpu_ms"],
            "batchFrameTime": lod_values["batch_ms"],
            "engineFrameTime": lod_values["engine_ms"],
            "drawcalls": 20,
            "triangles": 10000,
            "itemRendered": 50,
            "shadowRendered": int(profile["shadows"]),
            "gpuTextureMemory": 128,
            "gpuTextureResidentMemory": 64,
            "gpuTextureFramebufferMemory": 32,
            "texturePendingTransfers": 0,
        }.items()
    }
    return {
        "schema_version": 2,
        "platform": "macos",
        "fixture_version": "lit-grid-v1",
        "fixture_mode": fixture_mode,
        "profile_id": profile_id,
        "run_index": index,
        "quality_score": profile["quality_score"],
        "requested_profile": profile,
        "actual_profile": {field: profile[field] for field in PROFILE_FIELDS},
        "platform_info": {
            "computer": {"model": "Mac"},
            "cpu": {"model": "CPU"},
            "gpu": None if "Software" in renderer else {"model": renderer},
            "display": {"width": 1380},
            "platform": {"graphicsAPIs": [{"renderer": renderer}]},
            "deferred_capable": True,
        },
        "sample_count": len(samples),
        "samples_us": samples,
        "measurement_complete": True,
        "p95_frame_ms": p95,
        "p99_frame_ms": p95,
        "over_16_67_ms": 0,
        "over_33_33_ms": 0,
        "rates_hz": {
            "render": distribution(present),
            "present": distribution(present),
            "new_frame": distribution(present),
            "dropped": distribution(0),
            "simulation": distribution(60),
        },
        "stats": stats,
        "lod_timings_ms": lod_timings,
    }


def create_matrix(root: Path, *, mode: str, repeats: int, runner_class: str,
                  renderer: str, override: dict[tuple[str, int], tuple[float, float]] | None = None,
                  failed: set[tuple[str, int]] | None = None) -> list[str]:
    root.mkdir(parents=True)
    fixture_mode = "diagnostic-lite" if runner_class == "diagnostic" else "full"
    order_name = "diagnostic_order" if runner_class == "diagnostic" else f"{mode}_order"
    profiles = CATALOG[order_name]
    manifest = {
        "schema_version": 1,
        "mode": mode,
        "runner_class": runner_class,
        "fixture_mode": fixture_mode,
        "repeats": repeats,
        "expected_profiles": profiles,
        "application_sha256": "a" * 64,
        "profiles_sha256": hashlib.sha256(PROFILES.read_bytes()).hexdigest(),
        "machine": "x86_64" if runner_class == "diagnostic" else "arm64",
        "translated": False,
    }
    (root / "matrix-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    attempts = []
    for profile in profiles:
        if runner_class == "hardware":
            attempts.append({
                "profile": profile,
                "label": "warmup",
                "run_index": 1,
                "exit_code": 0,
                "accepted": True,
                "result_directory": f"{profile}/warmup",
            })
        for repeat in range(1, repeats + 1):
            directory = root / profile / f"run-{repeat}"
            directory.mkdir(parents=True)
            accepted = (profile, repeat) not in (failed or set())
            present, p95 = (override or {}).get((profile, repeat), (60.0, 12.0))
            if accepted:
                payload = run_result(profile, repeat + 1, present, p95, renderer, fixture_mode)
                (directory / "macos-profile.json").write_text(json.dumps(payload), encoding="utf-8")
                (directory / "profile-accepted").write_text("accepted\n", encoding="utf-8")
            attempts.append({
                "profile": profile,
                "label": f"run-{repeat}",
                "run_index": repeat + 1,
                "exit_code": 0 if accepted else 124,
                "accepted": accepted,
                "result_directory": f"{profile}/run-{repeat}",
            })
    (root / "attempts.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in attempts), encoding="utf-8"
    )
    return profiles


def analyze(matrix: Path, result: Path, junit: Path, repeats: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ANALYZER), str(matrix), "--profiles", str(PROFILES),
         "--result", str(result), "--junit", str(junit), "--minimum-runs", str(repeats)],
        text=True, capture_output=True, check=False,
    )


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    generated = temporary / "generated.js"
    generation = subprocess.run(
        [sys.executable, str(GENERATOR), "--profiles", str(PROFILES), "--profile", "forward-compat",
         "--template", str(TEMPLATE), "--output", str(generated), "--trace", str(temporary / "trace.gz"),
         "--run-index", "2"], text=True, capture_output=True, check=False,
    )
    assert generation.returncode == 0, generation.stderr
    assert generated.read_text(encoding="utf-8").startswith("var OVERTE_MACOS_PERFORMANCE_CASE = ")
    assert generated.stat().st_mode & 0o777 == 0o600

    diagnostic_generated = temporary / "diagnostic.js"
    diagnostic_generation = subprocess.run(
        [sys.executable, str(GENERATOR), "--profiles", str(PROFILES), "--profile", "forward-compat",
         "--template", str(TEMPLATE), "--output", str(diagnostic_generated),
         "--trace", str(temporary / "trace.gz"), "--run-index", "1",
         "--fixture-mode", "diagnostic-lite"], text=True, capture_output=True, check=False,
    )
    assert diagnostic_generation.returncode == 0, diagnostic_generation.stderr
    assert '"fixture_mode": "diagnostic-lite"' in diagnostic_generated.read_text(encoding="utf-8")

    rejected = subprocess.run(
        [sys.executable, str(GENERATOR), "--profiles", str(PROFILES), "--profile", "../escape",
         "--template", str(TEMPLATE), "--output", str(temporary / "bad.js"),
         "--trace", str(temporary / "trace.gz"), "--run-index", "1"],
        text=True, capture_output=True, check=False,
    )
    assert rejected.returncode != 0

    diagnostic = temporary / "diagnostic"
    create_matrix(diagnostic, mode="quick", repeats=1, runner_class="diagnostic",
                  renderer="Apple Software Renderer")
    diagnostic_result = temporary / "diagnostic-result.json"
    diagnostic_junit = temporary / "diagnostic.xml"
    diagnostic_analysis = analyze(diagnostic, diagnostic_result, diagnostic_junit, 1)
    assert diagnostic_analysis.returncode == 0, diagnostic_analysis.stdout + diagnostic_analysis.stderr
    summary = json.loads(diagnostic_result.read_text(encoding="utf-8"))
    assert summary["diagnostic_only"] is True
    assert summary["selected_profile"] is None
    assert summary["provisional_profile"] is None
    assert summary["diagnostic_profile"] == "forward-compat"
    assert summary["decision_ready"] is False
    assert summary["bottleneck_summary"] == {"forward-compat": "gpu"}
    assert summary["profiles"][0]["dominant_bottleneck"] == "gpu"
    assert summary["profiles"][0]["lod_timing_p95_ms_median"]["gpu_ms"] == 450.0

    quick = temporary / "quick"
    create_matrix(quick, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4")
    quick_result, quick_junit = temporary / "quick.json", temporary / "quick.xml"
    quick_analysis = analyze(quick, quick_result, quick_junit, 1)
    assert quick_analysis.returncode == 0, quick_analysis.stdout + quick_analysis.stderr
    quick_summary = json.loads(quick_result.read_text(encoding="utf-8"))
    assert quick_summary["decision_ready"] is False
    assert quick_summary["selected_profile"] is None
    assert quick_summary["provisional_profile"] == "deferred-balanced"
    assert set(quick_summary["bottleneck_summary"].values()) == {
        "balanced-or-refresh-limited"
    }

    full = temporary / "full"
    create_matrix(full, mode="full", repeats=3, runner_class="hardware", renderer="Apple M4")
    full_result, full_junit = temporary / "full.json", temporary / "full.xml"
    full_analysis = analyze(full, full_result, full_junit, 3)
    assert full_analysis.returncode == 0, full_analysis.stdout + full_analysis.stderr
    full_summary = json.loads(full_result.read_text(encoding="utf-8"))
    assert full_summary["decision_ready"] is True
    assert full_summary["selected_profile"] == "deferred-quality"

    outlier = temporary / "outlier"
    create_matrix(outlier, mode="full", repeats=3, runner_class="hardware", renderer="Apple M4",
                  override={("deferred-quality", 3): (1.0, 12.0)})
    outlier_result, outlier_junit = temporary / "outlier.json", temporary / "outlier.xml"
    outlier_analysis = analyze(outlier, outlier_result, outlier_junit, 3)
    assert outlier_analysis.returncode == 0, outlier_analysis.stdout + outlier_analysis.stderr
    assert json.loads(outlier_result.read_text(encoding="utf-8"))["selected_profile"] == "deferred-balanced"

    low_tail = temporary / "low-tail"
    create_matrix(low_tail, mode="full", repeats=3, runner_class="hardware", renderer="Apple M4")
    low_tail_path = low_tail / "deferred-quality/run-3/macos-profile.json"
    low_tail_payload = json.loads(low_tail_path.read_text(encoding="utf-8"))
    low_tail_payload["rates_hz"]["present"]["p10"] = 1
    low_tail_payload["rates_hz"]["present"]["min"] = 1
    low_tail_path.write_text(json.dumps(low_tail_payload), encoding="utf-8")
    low_tail_result, low_tail_junit = temporary / "low-tail.json", temporary / "low-tail.xml"
    low_tail_analysis = analyze(low_tail, low_tail_result, low_tail_junit, 3)
    assert low_tail_analysis.returncode == 0, low_tail_analysis.stdout + low_tail_analysis.stderr
    assert json.loads(low_tail_result.read_text(encoding="utf-8"))["selected_profile"] == "deferred-balanced"

    fallback = temporary / "fallback"
    overrides = {(profile, repeat): (30.0, 30.0)
                 for profile in CATALOG["full_order"] for repeat in range(1, 4)}
    create_matrix(fallback, mode="full", repeats=3, runner_class="hardware", renderer="Apple M4",
                  override=overrides)
    fallback_result, fallback_junit = temporary / "fallback.json", temporary / "fallback.xml"
    fallback_analysis = analyze(fallback, fallback_result, fallback_junit, 3)
    assert fallback_analysis.returncode != 0
    fallback_summary = json.loads(fallback_result.read_text(encoding="utf-8"))
    assert fallback_summary["selected_profile"] is None
    assert fallback_summary["fallback_profile_30hz"] == "deferred-quality"
    assert int(ET.parse(fallback_junit).getroot().attrib["failures"]) >= 1

    failed = temporary / "failed"
    create_matrix(failed, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4",
                  failed={("deferred-balanced", 1)})
    failed_result, failed_junit = temporary / "failed.json", temporary / "failed.xml"
    failed_analysis = analyze(failed, failed_result, failed_junit, 1)
    assert failed_analysis.returncode != 0
    assert json.loads(failed_result.read_text(encoding="utf-8"))["measurement_passed"] is False

    forged = temporary / "forged"
    create_matrix(forged, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4")
    forged_path = forged / "forward-compat/run-1/macos-profile.json"
    forged_payload = json.loads(forged_path.read_text(encoding="utf-8"))
    forged_payload["p95_frame_ms"] = 1
    forged_path.write_text(json.dumps(forged_payload), encoding="utf-8")
    forged_result, forged_junit = temporary / "forged.json", temporary / "forged.xml"
    forged_analysis = analyze(forged, forged_result, forged_junit, 1)
    assert forged_analysis.returncode != 0
    assert int(ET.parse(forged_junit).getroot().attrib["failures"]) >= 1

    forged_lod = temporary / "forged-lod"
    create_matrix(forged_lod, mode="quick", repeats=1,
                  runner_class="hardware", renderer="Apple M4")
    forged_lod_path = forged_lod / "forward-compat/run-1/macos-profile.json"
    forged_lod_payload = json.loads(forged_lod_path.read_text(encoding="utf-8"))
    forged_lod_payload["lod_timings_ms"]["gpu_ms"]["p95"] = 999
    forged_lod_payload["lod_timings_ms"]["gpu_ms"]["max"] = 999
    forged_lod_path.write_text(json.dumps(forged_lod_payload), encoding="utf-8")
    forged_lod_result = temporary / "forged-lod.json"
    forged_lod_junit = temporary / "forged-lod.xml"
    forged_lod_analysis = analyze(forged_lod, forged_lod_result, forged_lod_junit, 1)
    assert forged_lod_analysis.returncode != 0
    assert "lod_timings_ms.gpu_ms.p95 is inconsistent" in forged_lod_analysis.stdout

    missing_stats = temporary / "missing-stats"
    create_matrix(missing_stats, mode="quick", repeats=1,
                  runner_class="hardware", renderer="Apple M4")
    missing_stats_path = missing_stats / "forward-compat/run-1/macos-profile.json"
    missing_stats_payload = json.loads(missing_stats_path.read_text(encoding="utf-8"))
    del missing_stats_payload["stats"]["gpuFrameTime"]
    missing_stats_path.write_text(json.dumps(missing_stats_payload), encoding="utf-8")
    missing_stats_result = temporary / "missing-stats.json"
    missing_stats_junit = temporary / "missing-stats.xml"
    missing_stats_analysis = analyze(
        missing_stats, missing_stats_result, missing_stats_junit, 1
    )
    assert missing_stats_analysis.returncode != 0
    assert "stats.gpuFrameTime must be an object" in missing_stats_analysis.stdout

    mismatched = temporary / "mismatched"
    create_matrix(mismatched, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4")
    mismatched_path = mismatched / "forward-compat/run-1/macos-profile.json"
    mismatched_payload = json.loads(mismatched_path.read_text(encoding="utf-8"))
    mismatched_payload["actual_profile"]["viewport_scale"] = 0.5
    mismatched_path.write_text(json.dumps(mismatched_payload), encoding="utf-8")
    mismatch_result, mismatch_junit = temporary / "mismatch.json", temporary / "mismatch.xml"
    mismatch_analysis = analyze(mismatched, mismatch_result, mismatch_junit, 1)
    assert mismatch_analysis.returncode != 0

    rosetta = temporary / "rosetta"
    create_matrix(rosetta, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4")
    rosetta_manifest_path = rosetta / "matrix-manifest.json"
    rosetta_manifest = json.loads(rosetta_manifest_path.read_text(encoding="utf-8"))
    rosetta_manifest["translated"] = True
    rosetta_manifest_path.write_text(json.dumps(rosetta_manifest), encoding="utf-8")
    rosetta_result, rosetta_junit = temporary / "rosetta.json", temporary / "rosetta.xml"
    rosetta_analysis = analyze(rosetta, rosetta_result, rosetta_junit, 1)
    assert rosetta_analysis.returncode != 0
    assert "software or virtual renderer evidence" in rosetta_analysis.stdout

    stale = temporary / "stale"
    create_matrix(stale, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4")
    stale_dir = stale / "deferred-quality/run-99"
    stale_dir.mkdir(parents=True)
    (stale_dir / "profile-accepted").write_text("stale\n", encoding="utf-8")
    (stale_dir / "macos-profile.json").write_text("{}", encoding="utf-8")
    stale_result, stale_junit = temporary / "stale.json", temporary / "stale.xml"
    stale_analysis = analyze(stale, stale_result, stale_junit, 1)
    assert stale_analysis.returncode == 0, stale_analysis.stdout + stale_analysis.stderr
    assert json.loads(stale_result.read_text(encoding="utf-8"))["provisional_profile"] == "deferred-balanced"

    broken_warmup = temporary / "broken-warmup"
    create_matrix(broken_warmup, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4")
    warmup_rows = [json.loads(line) for line in
                   (broken_warmup / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    warmup_rows[0]["accepted"] = False
    warmup_rows[0]["exit_code"] = 139
    (broken_warmup / "attempts.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in warmup_rows), encoding="utf-8"
    )
    broken_warmup_result = temporary / "broken-warmup.json"
    broken_warmup_junit = temporary / "broken-warmup.xml"
    broken_warmup_analysis = analyze(
        broken_warmup, broken_warmup_result, broken_warmup_junit, 1
    )
    assert broken_warmup_analysis.returncode != 0
    assert "warmup failed with exit 139" in broken_warmup_analysis.stdout

    assert full_result.stat().st_mode & 0o777 == 0o600

print("macOS performance profile tool tests passed")
