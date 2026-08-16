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
LOCATION_SHA256 = "b" * 64
EVENT_ORDER = (
    "url_accepted", "domain_connected", "entity_server_active", "entity_query",
    "entity_data", "entity_decode", "entity_tree", "render_handoff",
    "first_presented", "first_visible",
)


def telemetry_lines(navigation_id: str, through: str = "first_visible",
                    first_visible_ms: int = 5000) -> str:
    lines = []
    emitted_events = EVENT_ORDER[:EVENT_ORDER.index(through) + 1]
    for index, event in enumerate(emitted_events):
        monotonic_us = 1_000_000 + (
            round(index * first_visible_ms * 1000 / (len(EVENT_ORDER) - 1))
            if through == "first_visible" else index * 100_000
        )
        tree_to_handoff_us = monotonic_us - (
            1_000_000 + (
                round(EVENT_ORDER.index("entity_tree") * first_visible_ms * 1000 /
                      (len(EVENT_ORDER) - 1))
                if through == "first_visible" else EVENT_ORDER.index("entity_tree") * 100_000
            )
        )
        first_render_phase_us = tree_to_handoff_us // 3
        second_render_phase_us = tree_to_handoff_us // 3
        server_active_us = 1_000_000 + (
            round(EVENT_ORDER.index("entity_server_active") * first_visible_ms * 1000 /
                  (len(EVENT_ORDER) - 1))
            if through == "first_visible"
            else EVENT_ORDER.index("entity_server_active") * 100_000
        )
        server_to_attempt_us = min(200_000, max(0, monotonic_us - server_active_us))
        details = {
            "entity_server_active": {"resource_loading": 1, "resource_pending": 2},
            "entity_query": {
                "bytes": 64,
                "resource_loading": 1,
                "resource_pending": 2,
                "server_to_first_attempt_us": server_to_attempt_us,
                "first_attempt_to_send_us": max(
                    0, monotonic_us - server_active_us - server_to_attempt_us
                ),
                "attempt_settings_loaded": 1,
                "attempt_physics_enabled": 0,
                "attempt_safe_landing_active": 1,
            },
            "entity_data": {"bytes": 1200, "packet_queue": 3},
            "entity_decode": {"decompress_us": 40, "wait_lock_us": 10},
            "entity_tree": {"entities": 8, "elements": 4, "tree_us": 500},
            "render_handoff": {
                "entities_pending_add": 7,
                "renderables_pending_update": 2,
                "tree_to_add_slot_us": first_render_phase_us,
                "add_slot_to_pending_pass_us": second_render_phase_us,
                "pending_pass_to_handoff_us": (
                    tree_to_handoff_us - first_render_phase_us - second_render_phase_us
                ),
                "adding_slots": 8,
                "preload_us": 1200,
                "add_passes": 2,
                "parent_incomplete_skips": 1,
            },
            "first_presented": {"present_count": 12},
            "first_visible": {"present_count": 13, "visible_count": 5},
        }.get(event, {})
        record = {
            "schema_version": 1,
            "navigation_id": navigation_id,
            "location_sha256": LOCATION_SHA256,
            "event": event,
            "monotonic_us": monotonic_us,
        }
        record.update(details)
        lines.append("[12:00:%02d.000] OVERTE_MACOS_ONLINE_NAV %s\n" % (
            index + 1,
            json.dumps(record, sort_keys=True),
        ))
    return "".join(lines)


def payload(mode: str, concurrency: int, index: int, first_visible: int,
            *, success: bool = True, runner_class: str = "hardware",
            diagnostic_observation: bool = False) -> dict[str, object]:
    snapshot = first_visible + 2000 if success else None
    idle = first_visible + 5000 if success else None
    return {
        "schema_version": 2,
        "platform": "macos",
        "navigation_id": f"c{concurrency}-p{index}-{mode}",
        "location_sha256": LOCATION_SHA256,
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
        "schema_version": 2,
        "runner_class": runner_class,
        "repeats": repeats,
        "location_label": "hub",
        "location_sha256": LOCATION_SHA256,
        "application_sha256": "a" * 64,
        "machine": "arm64" if runner_class == "hardware" else "x86_64",
        "translated": False,
        "executed_concurrencies": list(concurrencies),
        "requested_concurrencies": list(concurrencies),
        "public_world_informational": True,
        "navigation_after_startup": True,
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
                navigation_id = f"c{concurrency}-p{pair}-{mode}"
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
                    f"[12:00:06.000] OVERTE_MACOS_ONLINE_LOADING first_visible_ms={visible}\n" +
                    telemetry_lines(navigation_id, first_visible_ms=visible),
                    encoding="utf-8",
                )
                accepted = not failed_attempt
                if accepted:
                    (directory / "online-loading-accepted").write_text("accepted\n", encoding="utf-8")
                attempts.append({
                    "concurrency": concurrency,
                    "pair": pair,
                    "cache_mode": mode,
                    "navigation_id": navigation_id,
                    "exit_code": 124 if failed_attempt else 0,
                    "accepted": accepted,
                    "metrics_present": True,
                    "result_directory": str(directory.relative_to(root)),
                })
    (root / "attempts.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in attempts), encoding="utf-8"
    )


def mark_signal_attempt(root: Path, mode: str, *, metrics_present: bool) -> Path:
    directory = root / f"c10/pair-1/{mode}"
    attempts = [json.loads(line) for line in
                (root / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    for attempt in attempts:
        if attempt["concurrency"] == 10 and attempt["pair"] == 1 and attempt["cache_mode"] == mode:
            attempt.update({
                "exit_code": 139,
                "accepted": False,
                "metrics_present": metrics_present,
                "diagnostic_retry_attempted": False,
                "diagnostic_retry_exit_code": None,
            })
    (root / "attempts.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in attempts), encoding="utf-8"
    )
    (directory / "online-loading-accepted").unlink(missing_ok=True)
    (directory / "online-loading-process.json").write_text(json.dumps({
        "exit_code": -11,
        "timed_out": False,
        "sample_succeeded": False,
        "completion_file_observed": False,
        "terminated_after_completion": False,
    }), encoding="utf-8")
    return directory


def install_primary_checkpoint(directory: Path) -> None:
    final_path = directory / "macos-online-loading.json"
    checkpoint = json.loads(final_path.read_text(encoding="utf-8"))
    checkpoint.update({
        "evidence_stage": "first_visible_checkpoint",
        "reason": "first_visible_checkpoint",
        "success": False,
        "snapshot_requested_ms": None,
        "snapshot_completed_ms": None,
        "sustained_idle_ms": None,
        "completed_idle": False,
        "completed_snapshot": False,
        "duration_ms": checkpoint["first_visible_ms"],
    })
    checkpoint["queue_samples"][-1]["elapsed_ms"] = checkpoint["first_visible_ms"]
    (directory / "macos-online-loading-checkpoint.json").write_text(
        json.dumps(checkpoint), encoding="utf-8"
    )
    final_path.unlink()


def install_lldb_result(root: Path, directory: Path) -> None:
    final_path = directory / "macos-online-loading.json"
    source_path = final_path if final_path.is_file() else directory / "macos-online-loading-checkpoint.json"
    final = json.loads(source_path.read_text(encoding="utf-8"))
    final.update({
        "evidence_stage": "final",
        "reason": "diagnostic_observation_complete",
        "success": False,
    })
    lldb = directory / "lldb"
    lldb.mkdir()
    (lldb / "macos-online-loading.json").write_text(json.dumps(final), encoding="utf-8")
    (lldb / "online-loading-lldb.log").write_text(
        (directory / "online-loading.log").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (lldb / "online-loading-lldb-process.json").write_text(json.dumps({
        "exit_code": -15,
        "timed_out": False,
        "sample_succeeded": False,
        "completion_file_observed": True,
        "terminated_after_completion": True,
    }), encoding="utf-8")
    final_path.unlink(missing_ok=True)
    attempts = [json.loads(line) for line in
                (root / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    for attempt in attempts:
        if attempt["concurrency"] == 10 and attempt["pair"] == 1 and \
                attempt["cache_mode"] == directory.name:
            attempt["diagnostic_retry_attempted"] = True
            attempt["diagnostic_retry_exit_code"] = 0
    (root / "attempts.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in attempts), encoding="utf-8"
    )


def analyze(root: Path, result: Path, junit: Path, repeats: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ANALYZER), str(root), "--result", str(result),
         "--junit", str(junit), "--minimum-runs", str(repeats)],
        text=True, capture_output=True, check=False,
    )


def rewrite_telemetry_event(path: Path, event: str, update) -> None:
    prefix = "OVERTE_MACOS_ONLINE_NAV "
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    for index, line in enumerate(lines):
        prefix_at = line.find(prefix)
        if prefix_at < 0:
            continue
        record = json.loads(line[prefix_at + len(prefix):])
        if record.get("event") != event:
            continue
        update(record)
        lines[index] = line[:prefix_at + len(prefix)] + json.dumps(record, sort_keys=True)
        changed = True
        break
    assert changed, f"missing telemetry event {event}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary_name:
    temporary = Path(temporary_name)
    generated = temporary / "online.js"
    generation = subprocess.run(
        [sys.executable, str(GENERATOR), "--template", str(TEMPLATE), "--output", str(generated),
         "--cache-mode", "cold", "--concurrency", "10", "--run-index", "1",
         "--location-label", "hub", "--location-sha256", LOCATION_SHA256,
         "--navigation-id", "c10-p1-cold", "--runner-class", "hardware"],
        text=True, capture_output=True, check=False,
    )
    assert generation.returncode == 0, generation.stderr
    assert generated.read_text(encoding="utf-8").startswith("var OVERTE_MACOS_ONLINE_LOADING_CASE = ")
    assert generated.stat().st_mode & 0o777 == 0o600

    rejected = subprocess.run(
        [sys.executable, str(GENERATOR), "--template", str(TEMPLATE),
         "--output", str(temporary / "bad.js"), "--cache-mode", "warm",
         "--concurrency", "100", "--run-index", "1", "--location-label", "hub",
         "--location-sha256", LOCATION_SHA256, "--navigation-id", "c10-p1-warm",
         "--runner-class", "hardware"],
        text=True, capture_output=True, check=False,
    )
    assert rejected.returncode != 0

    unsafe_navigation = subprocess.run(
        [sys.executable, str(GENERATOR), "--template", str(TEMPLATE),
         "--output", str(temporary / "unsafe-navigation.js"), "--cache-mode", "warm",
         "--concurrency", "10", "--run-index", "1", "--location-label", "hub",
         "--location-sha256", LOCATION_SHA256, "--navigation-id", "https://token@secret.invalid/",
         "--runner-class", "hardware"],
        text=True, capture_output=True, check=False,
    )
    assert unsafe_navigation.returncode != 0
    assert "--navigation-id is invalid" in unsafe_navigation.stderr
    assert "secret.invalid" not in unsafe_navigation.stderr
    assert not (temporary / "unsafe-navigation.js").exists()

    unsafe_location = subprocess.run(
        [sys.executable, str(GENERATOR), "--template", str(TEMPLATE),
         "--output", str(temporary / "unsafe-location.js"), "--cache-mode", "warm",
         "--concurrency", "10", "--run-index", "1", "--location-label", "hub",
         "--location-sha256", "https://secret.invalid/", "--navigation-id", "c10-p1-warm",
         "--runner-class", "hardware"],
        text=True, capture_output=True, check=False,
    )
    assert unsafe_location.returncode != 0
    assert "--location-sha256 is invalid" in unsafe_location.stderr
    assert "secret.invalid" not in unsafe_location.stderr
    assert not (temporary / "unsafe-location.js").exists()

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
    assert all(group["queue_diagnostics"][0]["navigation_event_details"]["entity_decode"] == {
        "decompress_us": 40.0,
        "wait_lock_us": 10.0,
    } for group in summary["groups"])
    assert all(
        group["queue_diagnostics"][0]["navigation_event_details"]["render_handoff"]["add_passes"]
        == 2.0 for group in summary["groups"]
    )
    assert all(
        round(
            group["queue_diagnostics"][0]["tree_to_add_slot_ms"] +
            group["queue_diagnostics"][0]["add_slot_to_pending_pass_ms"] +
            group["queue_diagnostics"][0]["pending_pass_to_handoff_ms"],
            3,
        ) == group["queue_diagnostics"][0]["tree_to_handoff_ms"]
        for group in summary["groups"]
    )
    assert all(group["queue_diagnostics"][0]["render_preload_ms"] == 1.2
               for group in summary["groups"])
    assert all(
        round(
            group["queue_diagnostics"][0]["domain_to_entity_server_active_ms"] +
            group["queue_diagnostics"][0]["entity_server_active_to_query_ms"],
            3,
        ) == group["queue_diagnostics"][0]["domain_to_query_ms"]
        for group in summary["groups"]
    )
    assert all(
        round(
            group["queue_diagnostics"][0]["entity_server_active_to_first_query_attempt_ms"] +
            group["queue_diagnostics"][0]["first_query_attempt_to_send_ms"],
            3,
        ) == group["queue_diagnostics"][0]["entity_server_active_to_query_ms"]
        for group in summary["groups"]
    )
    assert all(group["queue_diagnostics"][0]["render_parent_incomplete_skips"] == 1.0
               for group in summary["groups"])
    assert all(group["queue_diagnostics"][0]["navigation_clock_skew_ms"] <= 1.0
               for group in summary["groups"])
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

    divergent_epoch = temporary / "divergent-epoch"
    create_benchmark(divergent_epoch, concurrencies=(10,))
    divergent_path = divergent_epoch / "c10/pair-1/cold/macos-online-loading.json"
    divergent_payload = json.loads(divergent_path.read_text(encoding="utf-8"))
    divergent_payload["first_visible_ms"] += 100000
    divergent_path.write_text(json.dumps(divergent_payload), encoding="utf-8")
    divergent_result = temporary / "divergent.json"
    divergent_junit = temporary / "divergent.xml"
    divergent_analysis = analyze(divergent_epoch, divergent_result, divergent_junit)
    assert divergent_analysis.returncode != 0
    assert "first-visible clocks diverge" in divergent_analysis.stdout

    wrong_interval = temporary / "wrong-interval"
    create_benchmark(wrong_interval, concurrencies=(10,))
    interval_path = wrong_interval / "c10/pair-1/cold/macos-online-loading.json"
    interval_payload = json.loads(interval_path.read_text(encoding="utf-8"))
    interval_payload["queue_sample_interval_ms"] = 250
    interval_path.write_text(json.dumps(interval_payload), encoding="utf-8")
    interval_result = temporary / "interval.json"
    interval_junit = temporary / "interval.xml"
    interval_analysis = analyze(wrong_interval, interval_result, interval_junit)
    assert interval_analysis.returncode != 0
    assert "sample interval must be exactly 500" in interval_analysis.stdout

    sequence_gap = temporary / "sequence-gap"
    create_benchmark(sequence_gap, concurrencies=(10,))
    gap_log = sequence_gap / "c10/pair-1/cold/online-loading.log"
    gap_log.write_text("\n".join(
        line for line in gap_log.read_text(encoding="utf-8").splitlines()
        if '"event": "entity_decode"' not in line
    ) + "\n", encoding="utf-8")
    gap_result, gap_junit = temporary / "gap.json", temporary / "gap.xml"
    gap_analysis = analyze(sequence_gap, gap_result, gap_junit)
    assert gap_analysis.returncode != 0
    assert "contiguous sequence" in gap_analysis.stdout

    wrong_navigation = temporary / "wrong-navigation"
    create_benchmark(wrong_navigation, concurrencies=(10,))
    wrong_log = wrong_navigation / "c10/pair-1/cold/online-loading.log"
    wrong_log.write_text(
        wrong_log.read_text(encoding="utf-8").replace(
            '"navigation_id": "c10-p1-cold"',
            '"navigation_id": "c10-p1-warm"',
            1,
        ),
        encoding="utf-8",
    )
    wrong_result, wrong_junit = temporary / "wrong.json", temporary / "wrong.xml"
    wrong_analysis = analyze(wrong_navigation, wrong_result, wrong_junit)
    assert wrong_analysis.returncode != 0
    assert "belongs to another navigation" in wrong_analysis.stdout

    unsafe_detail = temporary / "unsafe-detail"
    create_benchmark(unsafe_detail, concurrencies=(10,))
    unsafe_log = unsafe_detail / "c10/pair-1/cold/online-loading.log"
    unsafe_lines = unsafe_log.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(unsafe_lines):
        prefix_at = line.find("OVERTE_MACOS_ONLINE_NAV ")
        if prefix_at >= 0 and '"event": "entity_data"' in line:
            prefix = line[:prefix_at + len("OVERTE_MACOS_ONLINE_NAV ")]
            record = json.loads(line[len(prefix):])
            record["url"] = "https://token@secret.invalid/"
            unsafe_lines[index] = prefix + json.dumps(record, sort_keys=True)
            break
    unsafe_log.write_text("\n".join(unsafe_lines) + "\n", encoding="utf-8")
    unsafe_result, unsafe_junit = temporary / "unsafe.json", temporary / "unsafe.xml"
    unsafe_analysis = analyze(unsafe_detail, unsafe_result, unsafe_junit)
    assert unsafe_analysis.returncode != 0
    assert "unexpected field: url" in unsafe_analysis.stdout

    negative_detail = temporary / "negative-detail"
    create_benchmark(negative_detail, concurrencies=(10,))
    negative_log = negative_detail / "c10/pair-1/cold/online-loading.log"
    negative_log.write_text(
        negative_log.read_text(encoding="utf-8").replace('"packet_queue": 3', '"packet_queue": -3', 1),
        encoding="utf-8",
    )
    negative_result, negative_junit = temporary / "negative.json", temporary / "negative.xml"
    negative_analysis = analyze(negative_detail, negative_result, negative_junit)
    assert negative_analysis.returncode != 0
    assert "field packet_queue is negative" in negative_analysis.stdout

    missing_handoff_attribution = temporary / "missing-handoff-attribution"
    create_benchmark(missing_handoff_attribution, concurrencies=(10,))
    missing_handoff_log = (
        missing_handoff_attribution / "c10/pair-1/cold/online-loading.log"
    )
    rewrite_telemetry_event(
        missing_handoff_log,
        "render_handoff",
        lambda record: record.pop("parent_incomplete_skips"),
    )
    missing_handoff_result = temporary / "missing-handoff-attribution.json"
    missing_handoff_junit = temporary / "missing-handoff-attribution.xml"
    missing_handoff_analysis = analyze(
        missing_handoff_attribution, missing_handoff_result, missing_handoff_junit
    )
    assert missing_handoff_analysis.returncode != 0
    assert "missing attribution fields: parent_incomplete_skips" in missing_handoff_analysis.stdout

    inconsistent_handoff = temporary / "inconsistent-handoff-attribution"
    create_benchmark(inconsistent_handoff, concurrencies=(10,))
    inconsistent_handoff_log = inconsistent_handoff / "c10/pair-1/cold/online-loading.log"

    def add_unattributed_interval(record: dict[str, object]) -> None:
        record["pending_pass_to_handoff_us"] = (
            int(record["pending_pass_to_handoff_us"]) + 1000
        )

    rewrite_telemetry_event(
        inconsistent_handoff_log, "render_handoff", add_unattributed_interval
    )
    inconsistent_handoff_result = temporary / "inconsistent-handoff-attribution.json"
    inconsistent_handoff_junit = temporary / "inconsistent-handoff-attribution.xml"
    inconsistent_handoff_analysis = analyze(
        inconsistent_handoff, inconsistent_handoff_result, inconsistent_handoff_junit
    )
    assert inconsistent_handoff_analysis.returncode != 0
    assert "does not equal the entity_tree-to-handoff interval" in inconsistent_handoff_analysis.stdout

    impossible_single_pass_preload = temporary / "impossible-single-pass-preload"
    create_benchmark(impossible_single_pass_preload, concurrencies=(10,))
    impossible_preload_log = (
        impossible_single_pass_preload / "c10/pair-1/cold/online-loading.log"
    )

    def exceed_single_pass_interval(record: dict[str, object]) -> None:
        record["add_passes"] = 1
        record["preload_us"] = int(record["add_slot_to_pending_pass_us"]) + 1

    rewrite_telemetry_event(
        impossible_preload_log, "render_handoff", exceed_single_pass_interval
    )
    impossible_preload_result = temporary / "impossible-single-pass-preload.json"
    impossible_preload_junit = temporary / "impossible-single-pass-preload.xml"
    impossible_preload_analysis = analyze(
        impossible_single_pass_preload, impossible_preload_result, impossible_preload_junit
    )
    assert impossible_preload_analysis.returncode != 0
    assert "single-pass render_handoff preload exceeds" in impossible_preload_analysis.stdout

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

    checkpoint_crash = temporary / "diagnostic-checkpoint-crash"
    create_benchmark(
        checkpoint_crash, runner_class="diagnostic", concurrencies=(10,),
        diagnostic_partial=True,
    )
    checkpoint_directory = mark_signal_attempt(checkpoint_crash, "warm", metrics_present=True)
    install_primary_checkpoint(checkpoint_directory)
    checkpoint_result = temporary / "diagnostic-checkpoint-crash.json"
    checkpoint_junit = temporary / "diagnostic-checkpoint-crash.xml"
    checkpoint_analysis = analyze(checkpoint_crash, checkpoint_result, checkpoint_junit)
    assert checkpoint_analysis.returncode == 0, checkpoint_analysis.stdout + checkpoint_analysis.stderr
    checkpoint_summary = json.loads(checkpoint_result.read_text(encoding="utf-8"))
    assert checkpoint_summary["measurement_passed"] is False
    assert checkpoint_summary["diagnostic_observation_complete"] is True
    assert checkpoint_summary["failures"] == []
    assert checkpoint_summary["incomplete_attempts"] == ["c10/pair-1/warm failed with exit 139"]
    checkpoint_warm = next(group for group in checkpoint_summary["groups"]
                           if group["cache_mode"] == "warm")
    assert checkpoint_warm["crash_count"] == 1
    assert checkpoint_warm["diagnostic_evidence_sources"] == {"primary-checkpoint": 1}
    assert int(ET.parse(checkpoint_junit).getroot().attrib["failures"]) == 0

    lldb_crash = temporary / "diagnostic-lldb-crash"
    create_benchmark(
        lldb_crash, runner_class="diagnostic", concurrencies=(10,),
        diagnostic_partial=True,
    )
    lldb_directory = mark_signal_attempt(lldb_crash, "warm", metrics_present=True)
    install_lldb_result(lldb_crash, lldb_directory)
    lldb_result = temporary / "diagnostic-lldb-crash.json"
    lldb_junit = temporary / "diagnostic-lldb-crash.xml"
    lldb_analysis = analyze(lldb_crash, lldb_result, lldb_junit)
    assert lldb_analysis.returncode == 0, lldb_analysis.stdout + lldb_analysis.stderr
    lldb_summary = json.loads(lldb_result.read_text(encoding="utf-8"))
    lldb_warm = next(group for group in lldb_summary["groups"] if group["cache_mode"] == "warm")
    assert lldb_warm["crash_count"] == 1
    assert lldb_warm["diagnostic_evidence_sources"] == {"lldb-final": 1}
    assert lldb_summary["incomplete_attempts"] == ["c10/pair-1/warm failed with exit 139"]

    lldb_priority = temporary / "diagnostic-lldb-priority"
    create_benchmark(
        lldb_priority, runner_class="diagnostic", concurrencies=(10,),
        diagnostic_partial=True,
    )
    priority_directory = mark_signal_attempt(lldb_priority, "warm", metrics_present=True)
    install_primary_checkpoint(priority_directory)
    install_lldb_result(lldb_priority, priority_directory)
    priority_result = temporary / "diagnostic-lldb-priority.json"
    priority_junit = temporary / "diagnostic-lldb-priority.xml"
    priority_analysis = analyze(lldb_priority, priority_result, priority_junit)
    assert priority_analysis.returncode == 0, priority_analysis.stdout + priority_analysis.stderr
    priority_summary = json.loads(priority_result.read_text(encoding="utf-8"))
    priority_warm = next(group for group in priority_summary["groups"]
                         if group["cache_mode"] == "warm")
    assert priority_warm["diagnostic_evidence_sources"] == {"lldb-final": 1}

    for invalid_retry_field in (
            "retry_exit_code", "completion_file_observed", "terminated_after_completion", "timed_out"):
        invalid_lldb = temporary / f"invalid-lldb-{invalid_retry_field}"
        create_benchmark(
            invalid_lldb, runner_class="diagnostic", concurrencies=(10,),
            diagnostic_partial=True,
        )
        invalid_lldb_directory = mark_signal_attempt(invalid_lldb, "warm", metrics_present=True)
        install_lldb_result(invalid_lldb, invalid_lldb_directory)
        if invalid_retry_field == "retry_exit_code":
            attempts = [json.loads(line) for line in
                        (invalid_lldb / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
            for attempt in attempts:
                if attempt["cache_mode"] == "warm":
                    attempt["diagnostic_retry_exit_code"] = 124
            (invalid_lldb / "attempts.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in attempts),
                encoding="utf-8",
            )
        else:
            process_path = invalid_lldb_directory / "lldb/online-loading-lldb-process.json"
            process = json.loads(process_path.read_text(encoding="utf-8"))
            process[invalid_retry_field] = invalid_retry_field == "timed_out"
            process_path.write_text(json.dumps(process), encoding="utf-8")
        invalid_lldb_result = temporary / f"invalid-lldb-{invalid_retry_field}.json"
        invalid_lldb_junit = temporary / f"invalid-lldb-{invalid_retry_field}.xml"
        invalid_lldb_analysis = analyze(invalid_lldb, invalid_lldb_result, invalid_lldb_junit)
        assert invalid_lldb_analysis.returncode != 0
        assert "no controlled successful retry completion" in invalid_lldb_analysis.stdout

    for corrupt_field, corrupt_value, expected_error in (
            ("navigation_id", "c10-p1-cold", "navigation identity"),
            ("location_sha256", "c" * 64, "sanitized location identity")):
        invalid_checkpoint = temporary / f"invalid-checkpoint-{corrupt_field}"
        create_benchmark(
            invalid_checkpoint, runner_class="diagnostic", concurrencies=(10,),
            diagnostic_partial=True,
        )
        invalid_directory = mark_signal_attempt(invalid_checkpoint, "warm", metrics_present=True)
        install_primary_checkpoint(invalid_directory)
        invalid_path = invalid_directory / "macos-online-loading-checkpoint.json"
        invalid_payload = json.loads(invalid_path.read_text(encoding="utf-8"))
        invalid_payload[corrupt_field] = corrupt_value
        invalid_path.write_text(json.dumps(invalid_payload), encoding="utf-8")
        invalid_result = temporary / f"invalid-checkpoint-{corrupt_field}.json"
        invalid_junit = temporary / f"invalid-checkpoint-{corrupt_field}.xml"
        invalid_analysis = analyze(invalid_checkpoint, invalid_result, invalid_junit)
        assert invalid_analysis.returncode != 0
        assert expected_error in invalid_analysis.stdout

    incomplete_checkpoint = temporary / "incomplete-checkpoint-order"
    create_benchmark(
        incomplete_checkpoint, runner_class="diagnostic", concurrencies=(10,),
        diagnostic_partial=True,
    )
    incomplete_directory = mark_signal_attempt(incomplete_checkpoint, "warm", metrics_present=True)
    install_primary_checkpoint(incomplete_directory)
    incomplete_log = incomplete_directory / "online-loading.log"
    incomplete_log.write_text("\n".join(
        line for line in incomplete_log.read_text(encoding="utf-8").splitlines()
        if '"event": "entity_decode"' not in line
    ) + "\n", encoding="utf-8")
    incomplete_result = temporary / "incomplete-checkpoint-order.json"
    incomplete_junit = temporary / "incomplete-checkpoint-order.xml"
    incomplete_analysis = analyze(
        incomplete_checkpoint, incomplete_result, incomplete_junit
    )
    assert incomplete_analysis.returncode != 0
    assert "contiguous sequence" in incomplete_analysis.stdout

    pre_visible_crash = temporary / "diagnostic-pre-visible-crash"
    create_benchmark(
        pre_visible_crash, runner_class="diagnostic", concurrencies=(10,),
        diagnostic_partial=True,
    )
    pre_visible_directory = mark_signal_attempt(pre_visible_crash, "warm", metrics_present=False)
    (pre_visible_directory / "macos-online-loading.json").unlink()
    pre_visible_result = temporary / "diagnostic-pre-visible-crash.json"
    pre_visible_junit = temporary / "diagnostic-pre-visible-crash.xml"
    pre_visible_analysis = analyze(pre_visible_crash, pre_visible_result, pre_visible_junit)
    assert pre_visible_analysis.returncode != 0
    pre_visible_summary = json.loads(pre_visible_result.read_text(encoding="utf-8"))
    assert pre_visible_summary["passed"] is False
    assert pre_visible_summary["diagnostic_capture_complete"] is False
    assert "c10/pair-1/warm failed with exit 139" in pre_visible_summary["failures"]

    hardware_checkpoint = temporary / "hardware-checkpoint-crash"
    create_benchmark(hardware_checkpoint, runner_class="hardware", concurrencies=(10,))
    hardware_directory = mark_signal_attempt(hardware_checkpoint, "warm", metrics_present=True)
    install_primary_checkpoint(hardware_directory)
    hardware_checkpoint_result = temporary / "hardware-checkpoint-crash.json"
    hardware_checkpoint_junit = temporary / "hardware-checkpoint-crash.xml"
    hardware_checkpoint_analysis = analyze(
        hardware_checkpoint, hardware_checkpoint_result, hardware_checkpoint_junit
    )
    assert hardware_checkpoint_analysis.returncode != 0
    assert "no eligible evidence file exists" in hardware_checkpoint_analysis.stdout

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
        "[12:00:03.000] OVERTE_MACOS_ENTITY_GATE entity_query_sent\n" +
        telemetry_lines("c10-p1-cold", "entity_query"),
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
    assert set(render_summary["first_visible_latency_bottleneck_summary"].values()) == {
        "entity-server-or-query"
    }
    assert set(render_summary["post_visible_bottleneck_summary"].values()) == {
        "render-present"
    }
    assert all(group["queue_diagnostics"][0]["post_visible_zero_present_fraction"] == 1.0
               for group in render_summary["groups"])
    assert all(group["bottleneck_signal_counts"] == {
        "render-present": 1,
        "screenshot-incomplete": 1,
    }
               for group in render_summary["groups"])
    assert all(group["dominant_first_visible_latency_bottleneck"] ==
               "entity-server-or-query" for group in render_summary["groups"])
    assert all(group["dominant_post_visible_bottleneck"] == "render-present"
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
    assert missing_summary["passed"] is False
    assert any("navigation-scoped telemetry" in failure for failure in missing_summary["failures"])
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
