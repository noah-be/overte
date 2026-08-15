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
PROCEDURAL_SHADER = ROOT / "macos/tests/fixtures/profile-procedural.fs"
FIXTURE_SHA256 = hashlib.sha256(
    TEMPLATE.read_bytes() + b"\0" + PROCEDURAL_SHADER.read_bytes()
).hexdigest()
CATALOG = json.loads(PROFILES.read_text(encoding="utf-8"))
PROFILE_BY_ID = {profile["id"]: profile for profile in CATALOG["profiles"]}
PROFILE_FIELDS = (
    "render_method", "shadows", "haze", "bloom", "ambient_occlusion", "local_lighting",
    "procedural_materials", "antialiasing", "viewport_scale", "forward_samples",
)
FIXTURE_FEATURES = {
    "diagnostic-lite": ["semantic-red-cyan", "unlit-grid"],
    "full": [
        "ambient-occlusion-geometry", "antialiasing-edge-target",
        "bloom-emissive-material", "directional-shadow", "haze-zone",
        "lit-pbr-material", "local-point-lights", "procedural-material",
        "semantic-red-cyan",
    ],
}


def distribution(value: float) -> dict[str, float | int]:
    return {"count": 120, "mean": value, "min": value, "p10": value,
            "p50": value, "p95": value, "max": value}


def write_visual_evidence(directory: Path) -> str:
    screenshot = directory / "macos-profile.png"
    screenshot.write_bytes(b"deterministic semantic profile screenshot")
    digest = hashlib.sha256(screenshot.read_bytes()).hexdigest()
    (directory / "profile-screenshot.json").write_text(json.dumps({
        "passed": True,
        "failures": [],
        "red_pixels": 256,
        "cyan_pixels": 256,
        "red_centroid_x_ratio": 0.25,
        "cyan_centroid_x_ratio": 0.75,
    }), encoding="utf-8")
    return digest


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
        for offset in range(1, 121)
    ]
    lod_timings = {
        "sampling_interval_ms": 250,
        "semantics": "polled_latest_and_moving_averages",
        "raw_samples": lod_rows,
    }
    for name, value in lod_values.items():
        lod_timings[name] = {
            **distribution(value),
            "count": 120,
            "available": True,
            "invalid_count": 0,
            "zero_count": int(value == 0) * 120,
            "positive_count": int(value > 0) * 120,
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
        "schema_version": 3,
        "platform": "macos",
        "fixture_version": CATALOG["fixture_version"],
        "fixture_mode": fixture_mode,
        "fixture_features": FIXTURE_FEATURES[fixture_mode],
        "fixture_present_delta": 1 if fixture_mode == "diagnostic-lite" else 2,
        "fixture_sha256": FIXTURE_SHA256,
        "profile_id": profile_id,
        "run_index": index,
        "quality_score": profile["quality_score"],
        "requested_profile": profile,
        "actual_profile": {field: profile[field] for field in PROFILE_FIELDS},
        "platform_info": {
            "computer": {"model": "Mac"},
            "cpu": {"model": "CPU"},
            "gpu": None if "Software" in renderer else {"model": renderer},
            "display": {"modeWidth": 1380, "modeHeight": 776, "modeRefreshrate": 60},
            "platform": {"graphicsAPIs": [{"renderer": renderer, "vendor": "Apple"}]},
            "tier": 2,
            "deferred_capable": True,
        },
        "stress_entities": 13 if fixture_mode == "diagnostic-lite" else 52,
        "warmup_to_snapshot_ms": 15000,
        "duration_ms": 30000,
        "sample_count": len(samples),
        "frame_time_unit": "microseconds",
        "samples_us": samples,
        "measurement_complete": True,
        "mean_frame_ms": p95,
        "min_frame_ms": p95,
        "p50_frame_ms": p95,
        "p90_frame_ms": p95,
        "p95_frame_ms": p95,
        "p99_frame_ms": p95,
        "max_frame_ms": p95,
        "over_16_67_ms": 120 if p95 > 16.667 else 0,
        "over_33_33_ms": 120 if p95 > 33.333 else 0,
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
        "schema_version": 2,
        "mode": mode,
        "runner_class": runner_class,
        "fixture_mode": fixture_mode,
        "repeats": repeats,
        "expected_profiles": profiles,
        "application_sha256": "a" * 64,
        "profiles_sha256": hashlib.sha256(PROFILES.read_bytes()).hexdigest(),
        "fixture_sha256": FIXTURE_SHA256,
        "machine": "x86_64" if runner_class == "diagnostic" else "arm64",
        "translated": False,
    }
    (root / "matrix-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "application.sha256").write_text("a" * 64 + "  /fixture/Overte\n", encoding="utf-8")
    attempts = []
    for profile in profiles:
        if runner_class == "hardware":
            warmup_directory = root / profile / "warmup"
            warmup_directory.mkdir(parents=True)
            (warmup_directory / "profile-accepted").write_text("accepted\n", encoding="utf-8")
            warmup_screenshot_sha = write_visual_evidence(warmup_directory)
            attempts.append({
                "profile": profile,
                "label": "warmup",
                "run_index": 1,
                "exit_code": 0,
                "accepted": True,
                "result_directory": f"{profile}/warmup",
                "screenshot_sha256": warmup_screenshot_sha,
                "visual_validation_passed": True,
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
                screenshot_sha = write_visual_evidence(directory)
            else:
                screenshot_sha = None
            attempts.append({
                "profile": profile,
                "label": f"run-{repeat}",
                "run_index": repeat + 1,
                "exit_code": 0 if accepted else 124,
                "accepted": accepted,
                "result_directory": f"{profile}/run-{repeat}",
                "screenshot_sha256": screenshot_sha,
                "visual_validation_passed": accepted,
            })
    (root / "attempts.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in attempts), encoding="utf-8"
    )
    return profiles


def analyze(matrix: Path, result: Path, junit: Path, repeats: int,
            profiles: Path = PROFILES) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ANALYZER), str(matrix), "--profiles", str(profiles),
         "--fixture-source", str(TEMPLATE), "--procedural-shader", str(PROCEDURAL_SHADER),
         "--result", str(result), "--junit", str(junit), "--minimum-runs", str(repeats)],
        text=True, capture_output=True, check=False,
    )


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    generated = temporary / "generated.js"
    generation = subprocess.run(
        [sys.executable, str(GENERATOR), "--profiles", str(PROFILES), "--profile", "forward-compat",
         "--template", str(TEMPLATE), "--output", str(generated), "--trace", str(temporary / "trace.gz"),
         "--procedural-shader", str(PROCEDURAL_SHADER),
         "--run-index", "2"], text=True, capture_output=True, check=False,
    )
    assert generation.returncode == 0, generation.stderr
    generated_source = generated.read_text(encoding="utf-8")
    assert generated_source.startswith("var OVERTE_MACOS_PERFORMANCE_CASE = ")
    assert f'"fixture_sha256": "{FIXTURE_SHA256}"' in generated_source
    assert '"procedural-material"' in generated_source
    assert f'"procedural_shader_url": "{PROCEDURAL_SHADER.resolve().as_uri()}"' in generated_source
    assert generated.stat().st_mode & 0o777 == 0o600

    diagnostic_generated = temporary / "diagnostic.js"
    diagnostic_generation = subprocess.run(
        [sys.executable, str(GENERATOR), "--profiles", str(PROFILES), "--profile", "forward-compat",
         "--template", str(TEMPLATE), "--output", str(diagnostic_generated),
         "--procedural-shader", str(PROCEDURAL_SHADER),
         "--trace", str(temporary / "trace.gz"), "--run-index", "1",
         "--fixture-mode", "diagnostic-lite"], text=True, capture_output=True, check=False,
    )
    assert diagnostic_generation.returncode == 0, diagnostic_generation.stderr
    diagnostic_source = diagnostic_generated.read_text(encoding="utf-8")
    assert '"fixture_mode": "diagnostic-lite"' in diagnostic_source
    assert '"fixture_features": ["semantic-red-cyan", "unlit-grid"]' in diagnostic_source
    assert '"procedural-material"' not in diagnostic_source.split(";\n", 1)[0]

    rejected = subprocess.run(
        [sys.executable, str(GENERATOR), "--profiles", str(PROFILES), "--profile", "../escape",
         "--template", str(TEMPLATE), "--output", str(temporary / "bad.js"),
         "--procedural-shader", str(PROCEDURAL_SHADER),
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
    assert summary["selected_profile_60hz"] is None
    assert summary["provisional_profile"] is None
    assert summary["diagnostic_profile"] == "forward-compat"
    assert summary["decision_ready"] is False
    assert summary["bottleneck_summary"] == {"forward-compat": "gpu"}
    assert summary["profiles"][0]["dominant_bottleneck"] == "gpu"
    assert summary["profiles"][0]["lod_timing_p95_ms_median"]["gpu_ms"] == 450.0
    assert len(summary["hardware_key"]) == 64
    assert summary["hardware_identity"]["graphics_renderer"] == "Apple Software Renderer"
    assert "a" * 64 not in summary["hardware_key"]

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

    stable_key = temporary / "stable-hardware-key"
    stable_profiles = create_matrix(
        stable_key, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4"
    )
    stable_manifest_path = stable_key / "matrix-manifest.json"
    stable_manifest = json.loads(stable_manifest_path.read_text(encoding="utf-8"))
    stable_manifest["application_sha256"] = "b" * 64
    stable_manifest_path.write_text(json.dumps(stable_manifest), encoding="utf-8")
    (stable_key / "application.sha256").write_text(
        "b" * 64 + "  /private/runner/Overte\n", encoding="utf-8"
    )
    for profile in stable_profiles:
        path = stable_key / profile / "run-1/macos-profile.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["platform_info"]["platform"]["nics"] = [
            {"name": "en0", "mac": "SECRET-MAC-ADDRESS"}
        ]
        payload["platform_info"]["platform"]["graphicsAPIs"][0]["extensions"] = [
            "VOLATILE_EXTENSION"
        ]
        path.write_text(json.dumps(payload), encoding="utf-8")
    stable_result = temporary / "stable-hardware-key.json"
    stable_junit = temporary / "stable-hardware-key.xml"
    stable_analysis = analyze(stable_key, stable_result, stable_junit, 1)
    assert stable_analysis.returncode == 0, stable_analysis.stdout + stable_analysis.stderr
    stable_summary = json.loads(stable_result.read_text(encoding="utf-8"))
    assert stable_summary["hardware_key"] == quick_summary["hardware_key"]
    assert "SECRET" not in json.dumps(stable_summary["hardware_identity"])
    assert "VOLATILE" not in json.dumps(stable_summary["hardware_identity"])
    assert "b" * 64 not in stable_summary["hardware_key"]

    different_hardware = temporary / "different-hardware-key"
    create_matrix(
        different_hardware, mode="quick", repeats=1,
        runner_class="hardware", renderer="Apple M3",
    )
    different_result = temporary / "different-hardware-key.json"
    different_junit = temporary / "different-hardware-key.xml"
    different_analysis = analyze(different_hardware, different_result, different_junit, 1)
    assert different_analysis.returncode == 0, different_analysis.stdout
    different_summary = json.loads(different_result.read_text(encoding="utf-8"))
    assert different_summary["hardware_key"] != quick_summary["hardware_key"]

    full = temporary / "full"
    create_matrix(full, mode="full", repeats=3, runner_class="hardware", renderer="Apple M4")
    full_result, full_junit = temporary / "full.json", temporary / "full.xml"
    full_analysis = analyze(full, full_result, full_junit, 3)
    assert full_analysis.returncode == 0, full_analysis.stdout + full_analysis.stderr
    full_summary = json.loads(full_result.read_text(encoding="utf-8"))
    assert full_summary["decision_ready"] is True
    assert full_summary["selected_profile"] == "deferred-quality"
    assert full_summary["selected_profile_60hz"] == "deferred-quality"
    assert full_summary["fallback_profile_30hz"] is None

    full_single = temporary / "full-single"
    create_matrix(full_single, mode="full", repeats=1,
                  runner_class="hardware", renderer="Apple M4")
    full_single_result = temporary / "full-single.json"
    full_single_junit = temporary / "full-single.xml"
    full_single_analysis = analyze(
        full_single, full_single_result, full_single_junit, 1
    )
    assert full_single_analysis.returncode == 0, full_single_analysis.stdout
    full_single_summary = json.loads(full_single_result.read_text(encoding="utf-8"))
    assert full_single_summary["measurement_passed"] is True
    assert full_single_summary["decision_ready"] is False
    assert full_single_summary["selected_profile_60hz"] is None

    outlier = temporary / "outlier"
    create_matrix(outlier, mode="full", repeats=3, runner_class="hardware", renderer="Apple M4",
                  override={("deferred-quality", 3): (1.0, 12.0)})
    outlier_result, outlier_junit = temporary / "outlier.json", temporary / "outlier.xml"
    outlier_analysis = analyze(outlier, outlier_result, outlier_junit, 3)
    assert outlier_analysis.returncode == 0, outlier_analysis.stdout + outlier_analysis.stderr
    assert json.loads(outlier_result.read_text(encoding="utf-8"))["selected_profile"] == "deferred-balanced"

    spread = temporary / "spread"
    spread_overrides = {
        ("deferred-quality", 1): (60.0, 8.0),
        ("deferred-quality", 2): (60.0, 8.0),
        ("deferred-quality", 3): (60.0, 17.0),
    }
    create_matrix(spread, mode="full", repeats=3, runner_class="hardware",
                  renderer="Apple M4", override=spread_overrides)
    spread_result, spread_junit = temporary / "spread.json", temporary / "spread.xml"
    spread_analysis = analyze(spread, spread_result, spread_junit, 3)
    assert spread_analysis.returncode == 0, spread_analysis.stdout + spread_analysis.stderr
    spread_summary = json.loads(spread_result.read_text(encoding="utf-8"))
    assert spread_summary["selected_profile"] == "deferred-balanced"
    spread_profile = next(item for item in spread_summary["profiles"]
                          if item["profile_id"] == "deferred-quality")
    assert spread_profile["variation_60hz"]["metrics"]["frame_p95_ms"]["mad"] == 0
    assert spread_profile["variation_60hz"]["metrics"]["frame_p95_ms"]["spread"] == 9
    assert spread_profile["variation_60hz"]["passed"] is False

    high_mad = temporary / "high-mad"
    mad_overrides = {
        ("deferred-quality", 1): (60.0, 8.0),
        ("deferred-quality", 2): (60.0, 11.0),
        ("deferred-quality", 3): (60.0, 14.0),
    }
    create_matrix(high_mad, mode="full", repeats=3, runner_class="hardware",
                  renderer="Apple M4", override=mad_overrides)
    high_mad_result = temporary / "high-mad.json"
    high_mad_junit = temporary / "high-mad.xml"
    high_mad_analysis = analyze(high_mad, high_mad_result, high_mad_junit, 3)
    assert high_mad_analysis.returncode == 0, high_mad_analysis.stdout
    high_mad_summary = json.loads(high_mad_result.read_text(encoding="utf-8"))
    assert high_mad_summary["selected_profile"] == "deferred-balanced"
    high_mad_profile = next(item for item in high_mad_summary["profiles"]
                            if item["profile_id"] == "deferred-quality")
    assert high_mad_profile["variation_60hz"]["metrics"]["frame_p95_ms"]["spread"] == 6
    assert high_mad_profile["variation_60hz"]["metrics"]["frame_p95_ms"]["mad"] == 3
    assert high_mad_profile["variation_60hz"]["passed"] is False

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
    failed_summary = json.loads(failed_result.read_text(encoding="utf-8"))
    assert failed_summary.get("measurement_passed") is False, failed_analysis.stdout

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

    forged_visual = temporary / "forged-visual"
    create_matrix(
        forged_visual, mode="quick", repeats=1,
        runner_class="hardware", renderer="Apple M4",
    )
    forged_visual_attempts = [json.loads(line) for line in
        (forged_visual / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    forged_visual_attempts[1]["screenshot_sha256"] = "b" * 64
    (forged_visual / "attempts.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in forged_visual_attempts), encoding="utf-8"
    )
    forged_visual_result = temporary / "forged-visual.json"
    forged_visual_junit = temporary / "forged-visual.xml"
    forged_visual_analysis = analyze(
        forged_visual, forged_visual_result, forged_visual_junit, 1
    )
    assert forged_visual_analysis.returncode != 0
    assert "screenshot hash mismatch" in forged_visual_analysis.stdout

    missing_feature = temporary / "missing-fixture-feature"
    create_matrix(
        missing_feature, mode="quick", repeats=1,
        runner_class="hardware", renderer="Apple M4",
    )
    missing_feature_path = missing_feature / "forward-compat/run-1/macos-profile.json"
    missing_feature_payload = json.loads(missing_feature_path.read_text(encoding="utf-8"))
    missing_feature_payload["fixture_features"].remove("procedural-material")
    missing_feature_path.write_text(json.dumps(missing_feature_payload), encoding="utf-8")
    missing_feature_result = temporary / "missing-fixture-feature.json"
    missing_feature_junit = temporary / "missing-fixture-feature.xml"
    missing_feature_analysis = analyze(
        missing_feature, missing_feature_result, missing_feature_junit, 1
    )
    assert missing_feature_analysis.returncode != 0
    assert "fixture feature coverage mismatch" in missing_feature_analysis.stdout

    early_snapshot = temporary / "early-fixture-snapshot"
    create_matrix(
        early_snapshot, mode="quick", repeats=1,
        runner_class="hardware", renderer="Apple M4",
    )
    early_snapshot_path = early_snapshot / "forward-compat/run-1/macos-profile.json"
    early_snapshot_payload = json.loads(early_snapshot_path.read_text(encoding="utf-8"))
    early_snapshot_payload["fixture_present_delta"] = 1
    early_snapshot_path.write_text(json.dumps(early_snapshot_payload), encoding="utf-8")
    early_snapshot_result = temporary / "early-fixture-snapshot.json"
    early_snapshot_junit = temporary / "early-fixture-snapshot.xml"
    early_snapshot_analysis = analyze(
        early_snapshot, early_snapshot_result, early_snapshot_junit, 1
    )
    assert early_snapshot_analysis.returncode != 0
    assert "lacks post-warmup presents" in early_snapshot_analysis.stdout

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
    assert "statistics fields do not match schema 2" in missing_stats_analysis.stdout

    mismatched = temporary / "mismatched"
    create_matrix(mismatched, mode="quick", repeats=1, runner_class="hardware", renderer="Apple M4")
    mismatched_path = mismatched / "forward-compat/run-1/macos-profile.json"
    mismatched_payload = json.loads(mismatched_path.read_text(encoding="utf-8"))
    mismatched_payload["actual_profile"]["viewport_scale"] = 0.5
    mismatched_path.write_text(json.dumps(mismatched_payload), encoding="utf-8")
    mismatch_result, mismatch_junit = temporary / "mismatch.json", temporary / "mismatch.xml"
    mismatch_analysis = analyze(mismatched, mismatch_result, mismatch_junit, 1)
    assert mismatch_analysis.returncode != 0

    wrong_fixture = temporary / "wrong-fixture"
    create_matrix(wrong_fixture, mode="quick", repeats=1,
                  runner_class="hardware", renderer="Apple M4")
    wrong_fixture_path = wrong_fixture / "forward-compat/run-1/macos-profile.json"
    wrong_fixture_payload = json.loads(wrong_fixture_path.read_text(encoding="utf-8"))
    wrong_fixture_payload["fixture_version"] = "stale-fixture"
    wrong_fixture_path.write_text(json.dumps(wrong_fixture_payload), encoding="utf-8")
    wrong_fixture_result = temporary / "wrong-fixture.json"
    wrong_fixture_junit = temporary / "wrong-fixture.xml"
    wrong_fixture_analysis = analyze(
        wrong_fixture, wrong_fixture_result, wrong_fixture_junit, 1
    )
    assert wrong_fixture_analysis.returncode != 0
    assert "fixture mode mismatch" in wrong_fixture_analysis.stdout

    nonfinite = temporary / "nonfinite"
    create_matrix(nonfinite, mode="quick", repeats=1,
                  runner_class="hardware", renderer="Apple M4")
    nonfinite_path = nonfinite / "forward-compat/run-1/macos-profile.json"
    nonfinite_payload = json.loads(nonfinite_path.read_text(encoding="utf-8"))
    nonfinite_payload["samples_us"][0] = float("nan")
    nonfinite_path.write_text(json.dumps(nonfinite_payload), encoding="utf-8")
    nonfinite_result = temporary / "nonfinite.json"
    nonfinite_junit = temporary / "nonfinite.xml"
    nonfinite_analysis = analyze(nonfinite, nonfinite_result, nonfinite_junit, 1)
    assert nonfinite_analysis.returncode != 0
    assert "samples_us must be finite" in nonfinite_analysis.stdout

    wrong_app = temporary / "wrong-app"
    create_matrix(wrong_app, mode="quick", repeats=1,
                  runner_class="hardware", renderer="Apple M4")
    (wrong_app / "application.sha256").write_text("b" * 64 + "  /fixture/Overte\n",
                                                   encoding="utf-8")
    wrong_app_result = temporary / "wrong-app.json"
    wrong_app_junit = temporary / "wrong-app.xml"
    wrong_app_analysis = analyze(wrong_app, wrong_app_result, wrong_app_junit, 1)
    assert wrong_app_analysis.returncode != 0
    wrong_app_summary = json.loads(wrong_app_result.read_text(encoding="utf-8"))
    assert wrong_app_summary["measurement_passed"] is False
    assert wrong_app_summary["selected_profile_60hz"] is None
    wrong_app_suite = ET.parse(wrong_app_junit).getroot()
    assert int(wrong_app_suite.attrib["tests"]) >= 1
    assert int(wrong_app_suite.attrib["failures"]) >= 1

    wrong_catalog_hash = temporary / "wrong-catalog-hash"
    create_matrix(wrong_catalog_hash, mode="quick", repeats=1,
                  runner_class="hardware", renderer="Apple M4")
    wrong_catalog_manifest_path = wrong_catalog_hash / "matrix-manifest.json"
    wrong_catalog_manifest = json.loads(
        wrong_catalog_manifest_path.read_text(encoding="utf-8")
    )
    wrong_catalog_manifest["profiles_sha256"] = "b" * 64
    wrong_catalog_manifest_path.write_text(json.dumps(wrong_catalog_manifest), encoding="utf-8")
    wrong_catalog_result = temporary / "wrong-catalog-hash.json"
    wrong_catalog_junit = temporary / "wrong-catalog-hash.xml"
    wrong_catalog_analysis = analyze(
        wrong_catalog_hash, wrong_catalog_result, wrong_catalog_junit, 1
    )
    assert wrong_catalog_analysis.returncode != 0
    assert "catalog hash" in wrong_catalog_analysis.stdout

    wrong_fixture_hash = temporary / "wrong-fixture-hash"
    create_matrix(wrong_fixture_hash, mode="quick", repeats=1,
                  runner_class="hardware", renderer="Apple M4")
    wrong_fixture_manifest_path = wrong_fixture_hash / "matrix-manifest.json"
    wrong_fixture_manifest = json.loads(
        wrong_fixture_manifest_path.read_text(encoding="utf-8")
    )
    wrong_fixture_manifest["fixture_sha256"] = "b" * 64
    wrong_fixture_manifest_path.write_text(
        json.dumps(wrong_fixture_manifest), encoding="utf-8"
    )
    wrong_fixture_hash_result = temporary / "wrong-fixture-hash.json"
    wrong_fixture_hash_junit = temporary / "wrong-fixture-hash.xml"
    wrong_fixture_hash_analysis = analyze(
        wrong_fixture_hash, wrong_fixture_hash_result, wrong_fixture_hash_junit, 1
    )
    assert wrong_fixture_hash_analysis.returncode != 0
    assert "fixture source hash" in wrong_fixture_hash_analysis.stdout

    strict_catalog_path = temporary / "strict-profiles.json"
    strict_catalog = json.loads(PROFILES.read_text(encoding="utf-8"))
    strict_catalog["unexpected"] = True
    strict_catalog_path.write_text(json.dumps(strict_catalog), encoding="utf-8")
    strict_catalog_result = temporary / "strict-catalog.json"
    strict_catalog_junit = temporary / "strict-catalog.xml"
    strict_catalog_analysis = analyze(
        quick, strict_catalog_result, strict_catalog_junit, 1, strict_catalog_path
    )
    assert strict_catalog_analysis.returncode != 0
    assert "catalog fields do not match schema 1" in strict_catalog_analysis.stdout

    conflicting_renderer = temporary / "conflicting-renderer"
    conflicting_profiles = create_matrix(
        conflicting_renderer, mode="quick", repeats=1,
        runner_class="hardware", renderer="Apple M4",
    )
    for profile in conflicting_profiles:
        path = conflicting_renderer / profile / "run-1/macos-profile.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["platform_info"]["platform"]["graphicsAPIs"][0]["renderer"] = (
            "Apple Software Renderer"
        )
        path.write_text(json.dumps(payload), encoding="utf-8")
    conflicting_result = temporary / "conflicting-renderer.json"
    conflicting_junit = temporary / "conflicting-renderer.xml"
    conflicting_analysis = analyze(
        conflicting_renderer, conflicting_result, conflicting_junit, 1
    )
    assert conflicting_analysis.returncode != 0
    conflicting_summary = json.loads(conflicting_result.read_text(encoding="utf-8"))
    assert conflicting_summary["selected_profile"] is None
    assert conflicting_summary["fallback_profile_30hz"] is None

    unknown_renderer = temporary / "unknown-renderer"
    create_matrix(unknown_renderer, mode="quick", repeats=1,
                  runner_class="hardware", renderer="")
    unknown_result = temporary / "unknown-renderer.json"
    unknown_junit = temporary / "unknown-renderer.xml"
    unknown_analysis = analyze(unknown_renderer, unknown_result, unknown_junit, 1)
    assert unknown_analysis.returncode != 0
    unknown_summary = json.loads(unknown_result.read_text(encoding="utf-8"))
    assert unknown_summary["selected_profile"] is None
    assert unknown_summary["fallback_profile_30hz"] is None

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
    warmup_rows[0]["screenshot_sha256"] = None
    warmup_rows[0]["visual_validation_passed"] = False
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
