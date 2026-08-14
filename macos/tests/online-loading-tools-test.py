#!/usr/bin/env python3
"""Hermetic tests for online-loading case injection and aggregation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "macos/tools/render-online-loading-case.py"
ANALYZER = ROOT / "macos/tools/analyze-online-loading.py"
TEMPLATE = ROOT / "macos/tests/online-loading-benchmark.js"


def payload(mode: str, concurrency: int, index: int, first_visible: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "platform": "macos",
        "cache_mode": mode,
        "concurrency": concurrency,
        "run_index": index,
        "location_label": "hub",
        "duration_ms": first_visible + 6000,
        "first_entities_ms": first_visible - 100,
        "first_visible_ms": first_visible,
        "snapshot_requested_ms": first_visible + 1000,
        "snapshot_completed_ms": first_visible + 2000,
        "sustained_idle_ms": first_visible + 5000,
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
        "completed_idle": True,
        "completed_snapshot": True,
        "success": True,
        "reason": "visible_and_idle",
    }


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    generated = temporary / "online.js"
    generation = subprocess.run(
        [sys.executable, str(GENERATOR), "--template", str(TEMPLATE), "--output", str(generated),
         "--cache-mode", "cold", "--concurrency", "10", "--run-index", "1",
         "--location-label", "hub"],
        text=True, capture_output=True, check=False,
    )
    assert generation.returncode == 0, generation.stderr
    assert generated.read_text(encoding="utf-8").startswith("var OVERTE_MACOS_ONLINE_LOADING_CASE = ")
    assert generated.stat().st_mode & 0o777 == 0o600

    rejected = subprocess.run(
        [sys.executable, str(GENERATOR), "--template", str(TEMPLATE), "--output", str(temporary / "bad.js"),
         "--cache-mode", "warm", "--concurrency", "100", "--run-index", "1",
         "--location-label", "hub"],
        text=True, capture_output=True, check=False,
    )
    assert rejected.returncode != 0

    benchmark = temporary / "benchmark"
    for concurrency, cold_ms, warm_ms in ((10, 5000, 3500), (16, 4500, 2500)):
        for mode, visible in (("cold", cold_ms), ("warm", warm_ms)):
            directory = benchmark / f"c{concurrency}" / "pair-1" / mode
            directory.mkdir(parents=True)
            (directory / "macos-online-loading.json").write_text(
                json.dumps(payload(mode, concurrency, 1, visible)), encoding="utf-8"
            )
            (directory / "online-loading.log").write_text(
                "[12:00:00.000] start\n"
                "[12:00:01.000] OVERTE_MACOS_ENTITY_GATE domain_list_connected\n"
                "[12:00:02.000] OVERTE_MACOS_ENTITY_GATE entity_server_active\n"
                "[12:00:03.000] OVERTE_MACOS_ENTITY_GATE entity_query_sent\n"
                "[12:00:04.000] OVERTE_MACOS_ENTITY_GATE entity_data_received\n"
                "[12:00:05.000] OVERTE_MACOS_ENTITY_GATE render_handoff\n"
                "[12:00:06.000] OVERTE_MACOS_ONLINE_LOADING first_visible_ms=5000\n",
                encoding="utf-8",
            )
    result = temporary / "result.json"
    junit = temporary / "junit.xml"
    analysis = subprocess.run(
        [sys.executable, str(ANALYZER), str(benchmark), "--result", str(result),
         "--junit", str(junit), "--minimum-runs", "1"],
        text=True, capture_output=True, check=False,
    )
    assert analysis.returncode == 0, analysis.stderr + analysis.stdout
    summary = json.loads(result.read_text(encoding="utf-8"))
    assert summary["selected_concurrency"] == 16
    assert summary["public_world_informational"] is True
    assert result.stat().st_mode & 0o777 == 0o600

    corrupt = payload("cold", 10, 1, 5000)
    corrupt["queue_samples"][1]["elapsed_ms"] = 100
    corrupt_dir = temporary / "corrupt" / "c10" / "pair-1" / "cold"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "macos-online-loading.json").write_text(json.dumps(corrupt), encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, str(ANALYZER), str(temporary / "corrupt"),
         "--result", str(temporary / "corrupt.json"), "--junit", str(temporary / "corrupt.xml"),
         "--minimum-runs", "1"],
        text=True, capture_output=True, check=False,
    )
    assert failed.returncode != 0
    assert "strictly increasing" in failed.stdout

print("macOS online loading tool tests passed")
