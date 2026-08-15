#!/usr/bin/env python3
"""Hermetic contracts for online-loading generation and fail-closed aggregation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "macos/tools/render-online-loading-case.py"
ANALYZER = ROOT / "macos/tools/analyze-online-loading.py"
TEMPLATE = ROOT / "macos/tests/online-loading-benchmark.js"


def payload(mode: str, concurrency: int, index: int, first_visible: int,
            *, success: bool = True, runner_class: str = "hardware",
            diagnostic_observation: bool = False) -> dict[str, object]:
    snapshot = first_visible + 2000 if success else None
    idle = first_visible + 5000 if success else None
    return {
        "schema_version": 1,
        "platform": "macos",
        "cache_mode": mode,
        "concurrency": concurrency,
        "run_index": index,
        "location_label": "hub",
        "runner_class": runner_class,
        "duration_ms": first_visible + 6000,
        "first_entities_ms": first_visible - 100,
        "first_visible_ms": first_visible,
        "snapshot_requested_ms": first_visible + 1000,
        "snapshot_completed_ms": snapshot,
        "sustained_idle_ms": idle,
        "max_entity_count": 40,
        "queue_sample_interval_ms": 500,
        "queue_samples": [
            {"elapsed_ms": 500, "downloads": 2, "downloads_pending": 3, "processing": 1,
             "processing_pending": 0, "texture_pending_mb": 4, "entity_count": 0,
             "visible_count": 0, "present_hz": 60, "new_frame_hz": 60},
            {"elapsed_ms": first_visible + 5000, "downloads": 0, "downloads_pending": 0,
             "processing": 0, "processing_pending": 0, "texture_pending_mb": 0,
             "entity_count": 40, "visible_count": 20, "present_hz": 60, "new_frame_hz": 59},
        ],
        "completed_idle": success,
        "completed_snapshot": success,
        "success": success,
        "reason": (
            "visible_and_idle" if success else
            "diagnostic_observation_complete" if diagnostic_observation else
            "snapshot_timeout"
        ),
    }


def create_benchmark(root: Path, *, runner_class: str = "hardware",
                     concurrencies: tuple[int, ...] = (10, 16), repeats: int = 1,
                     failed: set[tuple[int, int, str]] | None = None,
                     diagnostic_partial: bool = False) -> None:
    root.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "runner_class": runner_class,
        "repeats": repeats,
        "location_label": "hub",
        "location_sha256": "b" * 64,
        "application_sha256": "a" * 64,
        "machine": "arm64" if runner_class == "hardware" else "x86_64",
        "translated": False,
        "executed_concurrencies": list(concurrencies),
        "requested_concurrencies": list(concurrencies),
        "public_world_informational": True,
    }
    (root / "online-loading-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    attempts: list[dict[str, object]] = []
    for concurrency in concurrencies:
        for pair in range(1, repeats + 1):
            for mode, visible in (("cold", 5000 - concurrency * 10),
                                  ("warm", 5000 - concurrency * 100)):
                directory = root / f"c{concurrency}" / f"pair-{pair}" / mode
                directory.mkdir(parents=True)
                failed_attempt = (concurrency, pair, mode) in (failed or set())
                incomplete_diagnostic = diagnostic_partial and runner_class == "diagnostic"
                (directory / "macos-online-loading.json").write_text(
                    json.dumps(payload(mode, concurrency, pair, visible,
                                       success=not failed_attempt and not incomplete_diagnostic,
                                       runner_class=runner_class,
                                       diagnostic_observation=incomplete_diagnostic)), encoding="utf-8"
                )
                (directory / "online-loading-process.json").write_text(json.dumps({
                    "exit_code": -15 if incomplete_diagnostic else 124 if failed_attempt else 0,
                    "timed_out": failed_attempt,
                    "sample_succeeded": False,
                    "completion_file_observed": incomplete_diagnostic,
                    "terminated_after_completion": incomplete_diagnostic,
                }), encoding="utf-8")
                (directory / "online-loading.log").write_text(
                    "[12:00:00.000] start\n"
                    "[12:00:01.000] OVERTE_MACOS_ENTITY_GATE domain_list_connected\n"
                    "[12:00:02.000] OVERTE_MACOS_ENTITY_GATE entity_server_active\n"
                    "[12:00:03.000] OVERTE_MACOS_ENTITY_GATE entity_query_sent\n"
                    "[12:00:04.000] OVERTE_MACOS_ENTITY_GATE entity_data_received\n"
                    "[12:00:05.000] OVERTE_MACOS_ENTITY_GATE render_handoff\n"
                    f"[12:00:06.000] OVERTE_MACOS_ONLINE_LOADING first_visible_ms={visible}\n",
                    encoding="utf-8",
                )
                accepted = not failed_attempt
                if accepted:
                    (directory / "online-loading-accepted").write_text("accepted\n", encoding="utf-8")
                attempts.append({
                    "concurrency": concurrency,
                    "pair": pair,
                    "cache_mode": mode,
                    "exit_code": 124 if failed_attempt else 0,
                    "accepted": accepted,
                    "metrics_present": True,
                    "result_directory": str(directory.relative_to(root)),
                })
    (root / "attempts.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in attempts), encoding="utf-8"
    )


def analyze(root: Path, result: Path, junit: Path, repeats: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ANALYZER), str(root), "--result", str(result),
         "--junit", str(junit), "--minimum-runs", str(repeats)],
        text=True, capture_output=True, check=False,
    )


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    generated = temporary / "online.js"
    generation = subprocess.run(
        [sys.executable, str(GENERATOR), "--template", str(TEMPLATE), "--output", str(generated),
         "--cache-mode", "cold", "--concurrency", "10", "--run-index", "1",
         "--location-label", "hub", "--runner-class", "hardware"],
        text=True, capture_output=True, check=False,
    )
    assert generation.returncode == 0, generation.stderr
    assert generated.read_text(encoding="utf-8").startswith("var OVERTE_MACOS_ONLINE_LOADING_CASE = ")
    assert generated.stat().st_mode & 0o777 == 0o600

    rejected = subprocess.run(
        [sys.executable, str(GENERATOR), "--template", str(TEMPLATE),
         "--output", str(temporary / "bad.js"), "--cache-mode", "warm",
         "--concurrency", "100", "--run-index", "1", "--location-label", "hub",
         "--runner-class", "hardware"],
        text=True, capture_output=True, check=False,
    )
    assert rejected.returncode != 0

    benchmark = temporary / "benchmark"
    create_benchmark(benchmark)
    result, junit = temporary / "result.json", temporary / "junit.xml"
    analysis = analyze(benchmark, result, junit)
    assert analysis.returncode == 0, analysis.stderr + analysis.stdout
    summary = json.loads(result.read_text(encoding="utf-8"))
    assert summary["measurement_passed"] is True
    assert summary["decision_ready"] is False
    assert summary["selected_concurrency"] is None
    assert summary["observed_best_concurrency"] == 16
    assert summary["public_world_informational"] is True
    assert set(summary["bottleneck_summary"].values()) == {"none-observed"}
    assert all(group["dominant_bottleneck"] == "none-observed" for group in summary["groups"])
    assert all(group["bottleneck_signal_counts"] == {} for group in summary["groups"])
    assert result.stat().st_mode & 0o777 == 0o600
    assert int(ET.parse(junit).getroot().attrib["failures"]) == 0

    partial = temporary / "partial"
    create_benchmark(partial, failed={(10, 1, "warm")})
    partial_result, partial_junit = temporary / "partial.json", temporary / "partial.xml"
    partial_analysis = analyze(partial, partial_result, partial_junit)
    assert partial_analysis.returncode != 0
    partial_summary = json.loads(partial_result.read_text(encoding="utf-8"))
    warm_ten = next(group for group in partial_summary["groups"]
                    if group["concurrency"] == 10 and group["cache_mode"] == "warm")
    assert warm_ten["metrics_count"] == 1
    assert warm_ten["valid_count"] == 0
    assert warm_ten["failure_count"] == 1
    assert warm_ten["timeout_count"] == 1
    assert warm_ten["first_visible_ms_median_partial"] is not None
    assert int(ET.parse(partial_junit).getroot().attrib["failures"]) >= 1

    corrupt = temporary / "corrupt"
    create_benchmark(corrupt, concurrencies=(10,))
    corrupt_path = corrupt / "c10/pair-1/cold/macos-online-loading.json"
    corrupt_payload = json.loads(corrupt_path.read_text(encoding="utf-8"))
    corrupt_payload["queue_samples"][1]["elapsed_ms"] = 100
    corrupt_path.write_text(json.dumps(corrupt_payload), encoding="utf-8")
    corrupt_result, corrupt_junit = temporary / "corrupt.json", temporary / "corrupt.xml"
    corrupt_analysis = analyze(corrupt, corrupt_result, corrupt_junit)
    assert corrupt_analysis.returncode != 0
    assert "strictly increasing" in corrupt_analysis.stdout
    assert int(ET.parse(corrupt_junit).getroot().attrib["failures"]) >= 1

    stale = temporary / "stale"
    create_benchmark(stale)
    stale_dir = stale / "c64/pair-99/cold"
    stale_dir.mkdir(parents=True)
    (stale_dir / "macos-online-loading.json").write_text("{}", encoding="utf-8")
    stale_result, stale_junit = temporary / "stale.json", temporary / "stale.xml"
    stale_analysis = analyze(stale, stale_result, stale_junit)
    assert stale_analysis.returncode == 0, stale_analysis.stdout + stale_analysis.stderr
    assert json.loads(stale_result.read_text(encoding="utf-8"))["attempt_count"] == 4

    diagnostic = temporary / "diagnostic"
    create_benchmark(diagnostic, runner_class="diagnostic", concurrencies=(10,))
    diagnostic_result, diagnostic_junit = temporary / "diagnostic.json", temporary / "diagnostic.xml"
    diagnostic_analysis = analyze(diagnostic, diagnostic_result, diagnostic_junit)
    assert diagnostic_analysis.returncode == 0, diagnostic_analysis.stdout + diagnostic_analysis.stderr
    diagnostic_summary = json.loads(diagnostic_result.read_text(encoding="utf-8"))
    assert diagnostic_summary["diagnostic_only"] is True
    assert diagnostic_summary["selected_concurrency"] is None
    assert diagnostic_summary["decision_ready"] is False
    assert diagnostic_summary["observed_best_concurrency"] == 10

    diagnostic_partial = temporary / "diagnostic-partial"
    create_benchmark(
        diagnostic_partial,
        runner_class="diagnostic",
        concurrencies=(10,),
        diagnostic_partial=True,
    )
    partial_diagnostic_result = temporary / "diagnostic-partial.json"
    partial_diagnostic_junit = temporary / "diagnostic-partial.xml"
    partial_diagnostic_analysis = analyze(
        diagnostic_partial, partial_diagnostic_result, partial_diagnostic_junit
    )
    assert partial_diagnostic_analysis.returncode == 0, (
        partial_diagnostic_analysis.stdout + partial_diagnostic_analysis.stderr
    )
    partial_diagnostic_summary = json.loads(
        partial_diagnostic_result.read_text(encoding="utf-8")
    )
    assert partial_diagnostic_summary["measurement_passed"] is False
    assert partial_diagnostic_summary["diagnostic_observation_complete"] is True
    assert partial_diagnostic_summary["passed"] is True
    assert partial_diagnostic_summary["failures"] == []
    assert partial_diagnostic_summary["incomplete_attempts"] == []
    assert partial_diagnostic_summary["diagnostic_capture_complete"] is True
    assert partial_diagnostic_summary["diagnostic_visibility_observed"] is True
    assert all(group["diagnostic_observation_count"] == 1
               for group in partial_diagnostic_summary["groups"])
    assert all(group["diagnostic_capture_count"] == 1
               for group in partial_diagnostic_summary["groups"])
    assert set(partial_diagnostic_summary["bottleneck_summary"].values()) == {
        "screenshot-completion"
    }
    partial_suite = ET.parse(partial_diagnostic_junit).getroot()
    assert int(partial_suite.attrib["failures"]) == 0
    assert int(partial_suite.attrib["skipped"]) >= 2

    mixed_diagnostic = temporary / "diagnostic-mixed"
    create_benchmark(
        mixed_diagnostic,
        runner_class="diagnostic",
        concurrencies=(10,),
        diagnostic_partial=True,
    )
    cold_metrics_path = mixed_diagnostic / "c10/pair-1/cold/macos-online-loading.json"
    cold_metrics = json.loads(cold_metrics_path.read_text(encoding="utf-8"))
    cold_metrics.update({
        "first_entities_ms": None,
        "first_visible_ms": None,
        "max_entity_count": 0,
        "reason": "visible_timeout",
    })
    cold_metrics_path.write_text(json.dumps(cold_metrics), encoding="utf-8")
    cold_log_path = mixed_diagnostic / "c10/pair-1/cold/online-loading.log"
    cold_log_path.write_text(
        "[12:00:00.000] start\n"
        "[12:00:01.000] OVERTE_MACOS_ENTITY_GATE domain_list_connected\n"
        "[12:00:03.000] OVERTE_MACOS_ENTITY_GATE entity_query_sent\n",
        encoding="utf-8",
    )
    mixed_result = temporary / "diagnostic-mixed.json"
    mixed_junit = temporary / "diagnostic-mixed.xml"
    mixed_analysis = analyze(mixed_diagnostic, mixed_result, mixed_junit)
    assert mixed_analysis.returncode == 0, mixed_analysis.stdout + mixed_analysis.stderr
    mixed_summary = json.loads(mixed_result.read_text(encoding="utf-8"))
    assert mixed_summary["diagnostic_observation_complete"] is True
    assert mixed_summary["diagnostic_visibility_observed"] is True
    cold_group = next(group for group in mixed_summary["groups"]
                      if group["cache_mode"] == "cold")
    warm_group = next(group for group in mixed_summary["groups"]
                      if group["cache_mode"] == "warm")
    assert cold_group["diagnostic_capture_count"] == 1
    assert cold_group["diagnostic_observation_count"] == 0
    assert cold_group["dominant_bottleneck"] == "entity-stream-or-public-domain"
    assert warm_group["diagnostic_observation_count"] == 1
    assert warm_group["dominant_bottleneck"] == "screenshot-completion"

    render_stall = temporary / "diagnostic-render-stall"
    create_benchmark(
        render_stall,
        runner_class="diagnostic",
        concurrencies=(10,),
        diagnostic_partial=True,
    )
    for mode in ("cold", "warm"):
        render_path = render_stall / f"c10/pair-1/{mode}/macos-online-loading.json"
        render_payload = json.loads(render_path.read_text(encoding="utf-8"))
        for sample in render_payload["queue_samples"]:
            if sample["elapsed_ms"] >= render_payload["first_visible_ms"]:
                sample["present_hz"] = 0
                sample["new_frame_hz"] = 0
        render_path.write_text(json.dumps(render_payload), encoding="utf-8")
    render_result = temporary / "diagnostic-render-stall.json"
    render_junit = temporary / "diagnostic-render-stall.xml"
    render_analysis = analyze(render_stall, render_result, render_junit)
    assert render_analysis.returncode == 0, render_analysis.stdout + render_analysis.stderr
    render_summary = json.loads(render_result.read_text(encoding="utf-8"))
    assert set(render_summary["bottleneck_summary"].values()) == {"render-present"}
    assert all(group["queue_diagnostics"][0]["post_visible_zero_present_fraction"] == 1.0
               for group in render_summary["groups"])
    assert all(group["bottleneck_signal_counts"] == {
        "render-present": 1,
        "screenshot-incomplete": 1,
    }
               for group in render_summary["groups"])

    missing_network = temporary / "diagnostic-missing-network"
    create_benchmark(
        missing_network,
        runner_class="diagnostic",
        concurrencies=(10,),
        diagnostic_partial=True,
    )
    missing_log = missing_network / "c10/pair-1/cold/online-loading.log"
    missing_log.write_text("[12:00:00.000] start\n", encoding="utf-8")
    missing_result = temporary / "diagnostic-missing-network.json"
    missing_junit = temporary / "diagnostic-missing-network.xml"
    missing_analysis = analyze(missing_network, missing_result, missing_junit)
    assert missing_analysis.returncode != 0
    missing_summary = json.loads(missing_result.read_text(encoding="utf-8"))
    assert missing_summary["diagnostic_capture_complete"] is False
    assert int(ET.parse(missing_junit).getroot().attrib["failures"]) >= 1

    mismatched_runner = temporary / "mismatched-runner"
    create_benchmark(mismatched_runner, runner_class="hardware", concurrencies=(10,))
    mismatched_path = mismatched_runner / "c10/pair-1/cold/macos-online-loading.json"
    mismatched_payload = json.loads(mismatched_path.read_text(encoding="utf-8"))
    mismatched_payload["runner_class"] = "diagnostic"
    mismatched_path.write_text(json.dumps(mismatched_payload), encoding="utf-8")
    mismatched_result = temporary / "mismatched-runner.json"
    mismatched_junit = temporary / "mismatched-runner.xml"
    mismatched_analysis = analyze(mismatched_runner, mismatched_result, mismatched_junit)
    assert mismatched_analysis.returncode != 0
    assert "runner class does not match" in mismatched_analysis.stdout

print("macOS online loading tool tests passed")
