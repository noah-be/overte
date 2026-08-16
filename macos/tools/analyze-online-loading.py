#!/usr/bin/env python3
"""Validate fresh cold/warm macOS online-loading attempts without hiding failures."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import tempfile
import xml.etree.ElementTree as ET


TIME = re.compile(r"(?<!\d)(\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?(?!\d)")
MARKERS = {
    "domain_connected": "OVERTE_MACOS_ENTITY_GATE domain_list_connected",
    "entity_server_active": "OVERTE_MACOS_ENTITY_GATE entity_server_active",
    "entity_query": "OVERTE_MACOS_ENTITY_GATE entity_query_sent",
    "entity_data": "OVERTE_MACOS_ENTITY_GATE entity_data_received",
    "render_handoff": "OVERTE_MACOS_ENTITY_GATE render_handoff",
    "first_visible": "OVERTE_MACOS_ONLINE_LOADING first_visible_ms=",
}
TELEMETRY_PREFIX = "OVERTE_MACOS_ONLINE_NAV "
SAFE_NAVIGATION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NAVIGATION_EVENT_ORDER = (
    "url_accepted",
    "domain_connected",
    "entity_server_active",
    "entity_query",
    "entity_data",
    "entity_decode",
    "entity_tree",
    "render_handoff",
    "first_presented",
    "first_visible",
)
NAVIGATION_EVENT_FIELDS = {
    "url_accepted": set(),
    "domain_connected": set(),
    "entity_server_active": {"resource_loading", "resource_pending"},
    "entity_query": {
        "bytes", "resource_loading", "resource_pending",
        "server_to_first_attempt_us", "first_attempt_to_send_us",
        "attempt_settings_loaded", "attempt_physics_enabled",
        "attempt_safe_landing_active",
    },
    "entity_data": {"bytes", "packet_queue"},
    "entity_decode": {"decompress_us", "wait_lock_us"},
    "entity_tree": {"entities", "elements", "tree_us"},
    "render_handoff": {
        "entities_pending_add", "renderables_pending_update",
        "tree_to_add_slot_us", "add_slot_to_pending_pass_us",
        "pending_pass_to_handoff_us", "adding_slots", "preload_us",
        "add_passes", "parent_incomplete_skips",
    },
    "first_presented": {"present_count"},
    "first_visible": {"present_count", "visible_count"},
}
RENDER_HANDOFF_ATTRIBUTION_FIELDS = (
    "tree_to_add_slot_us",
    "add_slot_to_pending_pass_us",
    "pending_pass_to_handoff_us",
    "adding_slots",
    "preload_us",
    "add_passes",
    "parent_incomplete_skips",
)


class LoadingError(RuntimeError):
    pass


def finite(value: object, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LoadingError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise LoadingError(f"{name} must be finite and >= {minimum}")
    return number


def integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LoadingError(f"{name} must be an integer >= {minimum}")
    return value


def is_signal_exit(exit_code: object) -> bool:
    return isinstance(exit_code, int) and not isinstance(exit_code, bool) and 128 < exit_code < 192


def load_object(path: Path, description: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LoadingError(f"could not read {description}: {error}") from error
    if not isinstance(payload, dict):
        raise LoadingError(f"{description} must be a JSON object")
    return payload


def time_seconds(line: str) -> float | None:
    match = TIME.search(line)
    if not match:
        return None
    hour, minute, second = (int(match.group(index)) for index in range(1, 4))
    fraction = match.group(4) or "0"
    return hour * 3600 + minute * 60 + second + int(fraction.ljust(6, "0")) / 1_000_000


def log_milestones(path: Path) -> dict[str, float | None]:
    result = {name: None for name in MARKERS}
    first_time: float | None = None
    previous: float | None = None
    day_offset = 0.0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return result
    for line in lines:
        moment = time_seconds(line)
        if moment is None:
            continue
        if previous is not None and moment + day_offset < previous - 12 * 3600:
            day_offset += 24 * 3600
        moment += day_offset
        previous = moment
        if first_time is None:
            first_time = moment
        for name, marker in MARKERS.items():
            if result[name] is None and marker in line:
                result[name] = moment
    if first_time is not None:
        for name, moment in list(result.items()):
            result[name] = None if moment is None else round((moment - first_time) * 1000, 3)
    return result


def navigation_milestones(path: Path, navigation_id: str,
                          location_sha256: str) -> tuple[dict[str, float | None], dict[str, dict[str, float]]]:
    """Load the test-gated JSON records; legacy process markers are not evidence."""
    if not SAFE_NAVIGATION_ID.fullmatch(navigation_id) or not SHA256.fullmatch(location_sha256):
        raise LoadingError("invalid expected navigation telemetry identity")
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        raise LoadingError(f"could not read online-loading telemetry: {error}") from error

    records: list[dict[str, object]] = []
    for number, line in enumerate(lines, 1):
        prefix_at = line.find(TELEMETRY_PREFIX)
        if prefix_at < 0:
            continue
        encoded = line[prefix_at + len(TELEMETRY_PREFIX):].strip()
        try:
            record = json.loads(encoded)
        except json.JSONDecodeError as error:
            raise LoadingError(f"invalid navigation telemetry line {number}: {error}") from error
        if not isinstance(record, dict) or record.get("schema_version") != 1:
            raise LoadingError(f"unsupported navigation telemetry line {number}")
        if record.get("navigation_id") != navigation_id:
            raise LoadingError(f"navigation telemetry line {number} belongs to another navigation")
        if record.get("location_sha256") != location_sha256:
            raise LoadingError(f"navigation telemetry line {number} has another location identity")
        event = record.get("event")
        if event not in NAVIGATION_EVENT_ORDER:
            raise LoadingError(f"navigation telemetry line {number} has an unknown event")
        allowed_fields = NAVIGATION_EVENT_FIELDS[str(event)]
        for key, value in record.items():
            if key in ("navigation_id", "location_sha256", "event"):
                if not isinstance(value, str):
                    raise LoadingError(f"navigation telemetry line {number} has an invalid identity field")
            elif key == "schema_version":
                if value != 1:
                    raise LoadingError(f"navigation telemetry line {number} has an invalid schema")
            elif key != "monotonic_us" and key not in allowed_fields:
                raise LoadingError(f"navigation telemetry line {number} has an unexpected field: {key}")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise LoadingError(f"navigation telemetry line {number} field {key} is not finite numeric data")
            elif float(value) < 0:
                raise LoadingError(f"navigation telemetry line {number} field {key} is negative")
        records.append(record)

    seen: set[str] = set()
    last_index = -1
    last_timestamp = -1.0
    by_event: dict[str, float] = {}
    for record in records:
        event = str(record["event"])
        if event in seen:
            raise LoadingError(f"duplicate navigation telemetry event: {event}")
        seen.add(event)
        event_index = NAVIGATION_EVENT_ORDER.index(event)
        if event_index != last_index + 1:
            expected = NAVIGATION_EVENT_ORDER[last_index + 1]
            raise LoadingError(f"navigation telemetry is not a contiguous sequence: expected {expected}, got {event}")
        timestamp = finite(record.get("monotonic_us"), f"{event}.monotonic_us")
        if timestamp <= last_timestamp:
            raise LoadingError("navigation telemetry times are not strictly increasing")
        last_index = event_index
        last_timestamp = timestamp
        by_event[event] = timestamp

    result: dict[str, float | None] = {event: None for event in NAVIGATION_EVENT_ORDER}
    if not records:
        return result, {}
    origin = by_event["url_accepted"]
    for event, timestamp in by_event.items():
        result[event] = round((timestamp - origin) / 1000.0, 3)
    details = {
        str(record["event"]): {
            key: float(value)
            for key, value in record.items()
            if key in NAVIGATION_EVENT_FIELDS[str(record["event"])]
        }
        for record in records
    }
    if "render_handoff" in by_event:
        handoff = details["render_handoff"]
        missing = [field for field in RENDER_HANDOFF_ATTRIBUTION_FIELDS if field not in handoff]
        if missing:
            raise LoadingError(
                "render_handoff is missing attribution fields: " + ", ".join(missing)
            )
        attributed_us = sum(handoff[field] for field in RENDER_HANDOFF_ATTRIBUTION_FIELDS[:3])
        tree_to_handoff_us = by_event["render_handoff"] - by_event["entity_tree"]
        if abs(attributed_us - tree_to_handoff_us) > 0.5:
            raise LoadingError(
                "render_handoff attribution does not equal the entity_tree-to-handoff interval"
            )
        if handoff["add_passes"] < 1:
            raise LoadingError("render_handoff attribution requires at least one add pass")
        if (handoff["add_passes"] == 1 and
                handoff["preload_us"] > handoff["add_slot_to_pending_pass_us"] + 0.5):
            raise LoadingError(
                "single-pass render_handoff preload exceeds its add-slot-to-pending-pass interval"
            )
    if "entity_query" in by_event:
        query = details["entity_query"]
        split_fields = (
            "server_to_first_attempt_us",
            "first_attempt_to_send_us",
            "attempt_settings_loaded",
            "attempt_physics_enabled",
            "attempt_safe_landing_active",
        )
        present_split_fields = [field for field in split_fields if field in query]
        if present_split_fields and len(present_split_fields) != len(split_fields):
            raise LoadingError("entity_query has an incomplete first-attempt attribution")
        if present_split_fields:
            if query["server_to_first_attempt_us"] < 0 or query["first_attempt_to_send_us"] < 0:
                raise LoadingError("entity_query first-attempt durations must be non-negative")
            for field in split_fields[2:]:
                if query[field] not in (0.0, 1.0):
                    raise LoadingError(f"entity_query {field} must be zero or one")
            attributed_us = query["server_to_first_attempt_us"] + query["first_attempt_to_send_us"]
            active_to_query_us = by_event["entity_query"] - by_event["entity_server_active"]
            if abs(attributed_us - active_to_query_us) > 5000.0:
                raise LoadingError(
                    "entity_query first-attempt attribution does not equal the entity-server-active-to-query interval"
                )
    return result, details


def sample_percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def queue_diagnostics(value: dict[str, object]) -> dict[str, object]:
    samples = value["queue_samples"]
    assert isinstance(samples, list)
    first_visible = value.get("first_visible_ms")
    visible_time = float(first_visible) if isinstance(first_visible, (int, float)) else None
    after_visible = [sample for sample in samples if visible_time is not None and
                     float(sample["elapsed_ms"]) >= visible_time]
    present = [float(sample["present_hz"]) for sample in after_visible]
    new_frame = [float(sample["new_frame_hz"]) for sample in after_visible]
    pending_area = 0.0
    texture_area = 0.0
    for previous, current in zip(samples, samples[1:]):
        seconds = (float(current["elapsed_ms"]) - float(previous["elapsed_ms"])) / 1000.0
        pending_area += float(previous["downloads_pending"]) * seconds
        texture_area += float(previous["texture_pending_mb"]) * seconds
    milestones = value.get("navigation_milestones_ms")
    milestones = milestones if isinstance(milestones, dict) else {}

    def delta(start: str, end: str) -> float | None:
        left, right = milestones.get(start), milestones.get(end)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)) and right >= left:
            return round(float(right) - float(left), 3)
        return None

    last = samples[-1]
    event_details = value.get("navigation_event_details", {})
    event_details = event_details if isinstance(event_details, dict) else {}
    handoff_details = event_details.get("render_handoff", {})
    handoff_details = handoff_details if isinstance(handoff_details, dict) else {}

    def handoff_milliseconds(field: str) -> float | None:
        value_us = handoff_details.get(field)
        return round(float(value_us) / 1000.0, 3) if isinstance(value_us, (int, float)) else None

    def query_milliseconds(field: str) -> float | None:
        value_us = event_details.get("entity_query", {}).get(field)
        return round(float(value_us) / 1000.0, 3) if isinstance(value_us, (int, float)) and value_us >= 0 else None

    diagnostics = {
        "sample_count": len(samples),
        "last_sample_ms": float(last["elapsed_ms"]),
        "peak_downloads": max(float(sample["downloads"]) for sample in samples),
        "peak_downloads_pending": max(float(sample["downloads_pending"]) for sample in samples),
        "peak_processing": max(float(sample["processing"]) for sample in samples),
        "peak_processing_pending": max(float(sample["processing_pending"]) for sample in samples),
        "peak_texture_pending_mb": max(float(sample["texture_pending_mb"]) for sample in samples),
        "pending_download_seconds": round(pending_area, 3),
        "texture_pending_mb_seconds": round(texture_area, 3),
        "final_downloads": float(last["downloads"]),
        "final_downloads_pending": float(last["downloads_pending"]),
        "final_processing": float(last["processing"]),
        "final_processing_pending": float(last["processing_pending"]),
        "final_texture_pending_mb": float(last["texture_pending_mb"]),
        "post_visible_present_hz_p10": sample_percentile(present, 0.10),
        "post_visible_present_hz_p50": sample_percentile(present, 0.50),
        "post_visible_new_frame_hz_p10": sample_percentile(new_frame, 0.10),
        "post_visible_new_frame_hz_p50": sample_percentile(new_frame, 0.50),
        "post_visible_zero_present_fraction": (
            sum(item <= 0.01 for item in present) / len(present) if present else None
        ),
        "domain_to_query_ms": delta("domain_connected", "entity_query"),
        "domain_to_entity_server_active_ms": delta(
            "domain_connected", "entity_server_active"
        ),
        "entity_server_active_to_query_ms": delta(
            "entity_server_active", "entity_query"
        ),
        "entity_server_active_to_first_query_attempt_ms": query_milliseconds(
            "server_to_first_attempt_us"
        ),
        "first_query_attempt_to_send_ms": query_milliseconds(
            "first_attempt_to_send_us"
        ),
        "query_to_data_ms": delta("entity_query", "entity_data"),
        "data_to_decode_ms": delta("entity_data", "entity_decode"),
        "decode_to_tree_ms": delta("entity_decode", "entity_tree"),
        "tree_to_handoff_ms": delta("entity_tree", "render_handoff"),
        "tree_to_add_slot_ms": handoff_milliseconds("tree_to_add_slot_us"),
        "add_slot_to_pending_pass_ms": handoff_milliseconds("add_slot_to_pending_pass_us"),
        "pending_pass_to_handoff_ms": handoff_milliseconds("pending_pass_to_handoff_us"),
        "render_preload_ms": handoff_milliseconds("preload_us"),
        "render_adding_slots": handoff_details.get("adding_slots"),
        "render_add_passes": handoff_details.get("add_passes"),
        "render_parent_incomplete_skips": handoff_details.get("parent_incomplete_skips"),
        "handoff_to_present_ms": delta("render_handoff", "first_presented"),
        "present_to_visible_ms": delta("first_presented", "first_visible"),
        "navigation_event_details": event_details,
        "navigation_clock_skew_ms": value.get("navigation_clock_skew_ms"),
    }
    signals: list[str] = []
    present_p50 = diagnostics["post_visible_present_hz_p50"]
    zero_present = diagnostics["post_visible_zero_present_fraction"]
    if (isinstance(present_p50, float) and present_p50 < 5.0 and
            isinstance(zero_present, float) and zero_present >= 0.5):
        signals.append("render-present")
    if any(float(last[name]) > 0 for name in (
            "downloads", "downloads_pending", "processing", "processing_pending",
            "texture_pending_mb")):
        signals.append("resource-backlog")
    if value.get("first_visible_ms") is not None and value.get("snapshot_completed_ms") is None:
        signals.append("screenshot-incomplete")

    # Keep time-to-first-visible attribution separate from the health of the
    # renderer after visibility.  A software renderer can reach a visible
    # entity after a slow domain query and then stop presenting; collapsing
    # both observations into one label hides the actionable loading phase.
    loading_phases = (
        ("domain_to_query_ms", "entity-server-or-query"),
        ("query_to_data_ms", "entity-stream-or-public-domain"),
        ("data_to_decode_ms", "entity-data-to-decode"),
        ("decode_to_tree_ms", "entity-tree-mutation"),
        ("tree_to_handoff_ms", "render-handoff"),
        ("handoff_to_present_ms", "first-present"),
        ("present_to_visible_ms", "first-visible"),
    )
    measured_loading_phases = [
        (float(diagnostics[field]), label)
        for field, label in loading_phases
        if isinstance(diagnostics[field], (int, float))
    ]
    if milestones.get("url_accepted") is None:
        loading_primary = "navigation-identity"
    elif milestones.get("domain_connected") is None:
        loading_primary = "domain-connection"
    elif milestones.get("entity_query") is None:
        loading_primary = "entity-server-or-query"
    elif milestones.get("entity_data") is None:
        loading_primary = "entity-stream-or-public-domain"
    elif value.get("first_visible_ms") is None:
        loading_primary = "entity-decode-or-visibility"
    elif measured_loading_phases:
        loading_primary = max(measured_loading_phases, key=lambda item: item[0])[1]
    else:
        loading_primary = "unattributed"

    if value.get("first_visible_ms") is None:
        post_visible_primary = "not-reached"
    elif "render-present" in signals:
        post_visible_primary = "render-present"
    elif value.get("snapshot_completed_ms") is None:
        post_visible_primary = "screenshot-completion"
    elif value.get("sustained_idle_ms") is None:
        post_visible_primary = "resource-backlog"
    else:
        post_visible_primary = "none-observed"

    if milestones.get("url_accepted") is None:
        primary = "navigation-identity"
    elif milestones.get("domain_connected") is None:
        primary = "domain-connection"
    elif milestones.get("entity_query") is None:
        primary = "entity-server-or-query"
    elif milestones.get("entity_data") is None:
        primary = "entity-stream-or-public-domain"
    elif value.get("first_visible_ms") is None:
        primary = "entity-decode-or-visibility"
    elif value.get("snapshot_completed_ms") is None:
        primary = "render-present" if isinstance(present_p50, float) and present_p50 < 5.0 else (
            "screenshot-completion"
        )
    elif value.get("sustained_idle_ms") is None:
        primary = "resource-backlog"
    else:
        primary = "none-observed"
    diagnostics["primary_bottleneck"] = primary
    diagnostics["first_visible_latency_bottleneck"] = loading_primary
    diagnostics["post_visible_bottleneck"] = post_visible_primary
    diagnostics["bottleneck_signals"] = signals
    return diagnostics


def load_manifest(root: Path) -> dict[str, object]:
    manifest = load_object(root / "online-loading-manifest.json", "online-loading manifest")
    if manifest.get("schema_version") != 2 or manifest.get("runner_class") not in ("diagnostic", "hardware"):
        raise LoadingError("unsupported online-loading manifest")
    if manifest.get("navigation_after_startup") is not True:
        raise LoadingError("online benchmark must begin navigation after the ready-app baseline")
    repeats = integer(manifest.get("repeats"), "manifest repeats", minimum=1)
    concurrencies = manifest.get("executed_concurrencies")
    if (not isinstance(concurrencies, list) or not concurrencies or
            any(not isinstance(value, int) or not 1 <= value <= 64 for value in concurrencies) or
            len(set(concurrencies)) != len(concurrencies)):
        raise LoadingError("manifest has invalid executed concurrencies")
    app_sha = manifest.get("application_sha256")
    location_sha = manifest.get("location_sha256")
    if not isinstance(app_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", app_sha):
        raise LoadingError("manifest has no valid application SHA-256")
    if not isinstance(location_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", location_sha):
        raise LoadingError("manifest has no sanitized location identity")
    if manifest.get("public_world_informational") is not True:
        raise LoadingError("online benchmark must classify mutable public-world evidence")
    manifest["repeats"] = repeats
    return manifest


def load_attempts(root: Path, manifest: dict[str, object]) -> tuple[list[dict[str, object]], list[str]]:
    try:
        lines = (root / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise LoadingError(f"could not read online attempt manifest: {error}") from error
    attempts: list[dict[str, object]] = []
    for number, line in enumerate(lines, 1):
        try:
            attempt = json.loads(line)
        except json.JSONDecodeError as error:
            raise LoadingError(f"invalid online attempt record {number}: {error}") from error
        if not isinstance(attempt, dict):
            raise LoadingError(f"online attempt record {number} must be an object")
        concurrency = integer(attempt.get("concurrency"), f"attempt {number} concurrency", minimum=1)
        pair = integer(attempt.get("pair"), f"attempt {number} pair", minimum=1)
        if concurrency not in manifest["executed_concurrencies"] or pair > manifest["repeats"]:
            raise LoadingError(f"online attempt record {number} is outside the immutable plan")
        if attempt.get("cache_mode") not in ("cold", "warm"):
            raise LoadingError(f"online attempt record {number} has invalid cache mode")
        expected_navigation_id = f"c{concurrency}-p{pair}-{attempt['cache_mode']}"
        if attempt.get("navigation_id") != expected_navigation_id:
            raise LoadingError(f"online attempt record {number} has an invalid navigation identity")
        exit_code = integer(attempt.get("exit_code"), f"attempt {number} exit_code")
        if not isinstance(attempt.get("accepted"), bool) or not isinstance(attempt.get("metrics_present"), bool):
            raise LoadingError(f"online attempt record {number} has invalid evidence flags")
        if attempt["accepted"] != (exit_code == 0):
            raise LoadingError(f"online attempt record {number} acceptance and exit status disagree")
        retry_attempted = attempt.get("diagnostic_retry_attempted", False)
        retry_exit_code = attempt.get("diagnostic_retry_exit_code")
        if not isinstance(retry_attempted, bool):
            raise LoadingError(f"online attempt record {number} has an invalid diagnostic retry flag")
        if retry_attempted:
            if (manifest["runner_class"] != "diagnostic" or not is_signal_exit(exit_code) or
                    isinstance(retry_exit_code, bool) or not isinstance(retry_exit_code, int) or
                    retry_exit_code < 0):
                raise LoadingError(f"online attempt record {number} has invalid diagnostic retry evidence")
        elif retry_exit_code is not None:
            raise LoadingError(f"online attempt record {number} has an unexpected diagnostic retry exit")
        relative = attempt.get("result_directory")
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise LoadingError(f"online attempt record {number} has unsafe result directory")
        attempt["resolved_directory"] = root / relative
        attempts.append(attempt)

    failures: list[str] = []
    for concurrency in manifest["executed_concurrencies"]:
        for pair in range(1, int(manifest["repeats"]) + 1):
            for cache_mode in ("cold", "warm"):
                matches = [item for item in attempts if item["concurrency"] == concurrency and
                           item["pair"] == pair and item["cache_mode"] == cache_mode]
                if len(matches) != 1:
                    failures.append(f"c{concurrency}/pair-{pair}/{cache_mode} has {len(matches)} records")
                elif not matches[0]["accepted"]:
                    failures.append(
                        f"c{concurrency}/pair-{pair}/{cache_mode} failed with exit {matches[0]['exit_code']}"
                    )
    expected = len(manifest["executed_concurrencies"]) * int(manifest["repeats"]) * 2
    if len(attempts) != expected:
        failures.append(f"online benchmark has {len(attempts)} attempts instead of {expected}")
    return attempts, failures


def load_signal_process(path: Path, attempt: dict[str, object]) -> dict[str, object]:
    process = load_object(path, "primary signal process result")
    exit_code = process.get("exit_code")
    expected = -(int(attempt["exit_code"]) - 128)
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code != expected:
        raise LoadingError("primary process result does not prove the recorded signal exit")
    if process.get("timed_out") is True or process.get("completion_file_observed") is True:
        raise LoadingError("primary signal process result has contradictory completion state")
    return process


def validate_metrics_candidate(attempt: dict[str, object], manifest: dict[str, object], *,
                               metrics_path: Path, log_path: Path, process_path: Path,
                               evidence_source: str,
                               primary_signal_process: dict[str, object] | None) -> dict[str, object]:
    payload = load_object(metrics_path, f"{evidence_source} online-loading metrics")
    if payload.get("schema_version") != 2 or payload.get("platform") != "macos":
        raise LoadingError("unsupported online-loading result")
    if (payload.get("cache_mode") != attempt["cache_mode"] or
            payload.get("concurrency") != attempt["concurrency"] or
            payload.get("run_index") != attempt["pair"]):
        raise LoadingError("online-loading result does not match its attempt")
    if payload.get("navigation_id") != attempt["navigation_id"]:
        raise LoadingError("online-loading result does not match its navigation identity")
    if payload.get("location_sha256") != manifest["location_sha256"]:
        raise LoadingError("online-loading result does not match its sanitized location identity")
    if payload.get("runner_class") != manifest["runner_class"]:
        raise LoadingError("online-loading result runner class does not match its manifest")
    if not isinstance(payload.get("success"), bool) or not isinstance(payload.get("reason"), str):
        raise LoadingError("online-loading result has invalid completion fields")
    evidence_stage = payload.get("evidence_stage")
    if evidence_source == "primary-checkpoint":
        if (evidence_stage != "first_visible_checkpoint" or
                payload.get("reason") != "first_visible_checkpoint" or
                payload.get("success") is not False or
                payload.get("snapshot_requested_ms") is not None or
                payload.get("snapshot_completed_ms") is not None or
                payload.get("sustained_idle_ms") is not None or
                payload.get("completed_idle") is not False or
                payload.get("completed_snapshot") is not False):
            raise LoadingError("first-visible checkpoint has invalid evidence-stage fields")
    elif evidence_stage not in (None, "final"):
        raise LoadingError("final online-loading result has an invalid evidence stage")
    samples = payload.get("queue_samples")
    if not isinstance(samples, list) or not samples or len(samples) > 1000:
        raise LoadingError("invalid online queue samples")
    previous = -1.0
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise LoadingError(f"queue sample {index} is not an object")
        elapsed = finite(sample.get("elapsed_ms"), f"queue_samples[{index}].elapsed_ms")
        if elapsed <= previous:
            raise LoadingError("queue sample times are not strictly increasing")
        previous = elapsed
        for key in ("downloads", "downloads_pending", "processing", "processing_pending",
                    "texture_pending_mb", "entity_count", "visible_count", "present_hz", "new_frame_hz"):
            finite(sample.get(key), f"queue_samples[{index}].{key}")
    for name in ("first_entities_ms", "first_visible_ms", "snapshot_completed_ms", "sustained_idle_ms"):
        if payload.get(name) is not None:
            finite(payload[name], name)
    navigation_values, navigation_details = navigation_milestones(
        log_path,
        str(payload["navigation_id"]),
        str(payload["location_sha256"]),
    )
    payload["navigation_milestones_ms"] = navigation_values
    payload["navigation_event_details"] = navigation_details
    # Retain old wall-clock markers for troubleshooting only. They are neither
    # navigation-scoped nor used for validation, completion, or bottleneck decisions.
    payload["legacy_host_milestones_ms"] = log_milestones(log_path)
    if navigation_values["url_accepted"] is None:
        raise LoadingError("online-loading result has no navigation-scoped telemetry")
    if payload.get("first_visible_ms") is not None and navigation_values["first_visible"] is None:
        raise LoadingError("online-loading result claims visibility without a navigation-scoped milestone")
    interval_ms = integer(payload.get("queue_sample_interval_ms"), "queue_sample_interval_ms", minimum=1)
    if interval_ms != 500:
        raise LoadingError("online-loading queue sample interval must be exactly 500 ms")
    if payload.get("first_visible_ms") is not None:
        core_visible_ms = finite(navigation_values["first_visible"], "navigation.first_visible")
        script_visible_ms = finite(payload["first_visible_ms"], "first_visible_ms")
        clock_skew_ms = abs(core_visible_ms - script_visible_ms)
        if clock_skew_ms > interval_ms + 250:
            raise LoadingError("navigation and script first-visible clocks diverge")
        payload["navigation_clock_skew_ms"] = round(clock_skew_ms, 3)
    else:
        payload["navigation_clock_skew_ms"] = None
    if payload.get("first_visible_ms") is not None and any(
            navigation_values[event] is None for event in NAVIGATION_EVENT_ORDER):
        raise LoadingError("visible online-loading evidence has an incomplete navigation event sequence")
    if evidence_source == "primary-checkpoint":
        if (payload.get("first_visible_ms") is None or
                integer(payload.get("max_entity_count"), "max_entity_count", minimum=1) < 1):
            raise LoadingError("first-visible checkpoint does not contain visible entity evidence")
    process = load_object(process_path, f"{evidence_source} process result")
    if evidence_source == "lldb-final" and (
            attempt.get("diagnostic_retry_exit_code") != 0 or
            process.get("completion_file_observed") is not True or
            process.get("terminated_after_completion") is not True or
            process.get("timed_out") is not False):
        raise LoadingError("LLDB final result has no controlled successful retry completion")
    payload["process_exit_code"] = process.get("exit_code")
    payload["process_timed_out"] = process.get("timed_out") is True
    payload["process_sample_succeeded"] = process.get("sample_succeeded") is True
    payload["process_completion_file_observed"] = process.get("completion_file_observed") is True
    payload["diagnostic_evidence_source"] = evidence_source
    payload["diagnostic_signal_evidence"] = (
        primary_signal_process is not None and evidence_source.startswith("primary-")
    )
    payload["primary_signal_exit_code"] = (
        attempt["exit_code"] if primary_signal_process is not None else None
    )
    payload["queue_diagnostics"] = queue_diagnostics(payload)
    return payload


def load_metrics(attempt: dict[str, object], manifest: dict[str, object]) -> dict[str, object] | None:
    directory = attempt["resolved_directory"]
    if not attempt["metrics_present"]:
        return None
    signal_diagnostic = (
        manifest["runner_class"] == "diagnostic" and is_signal_exit(attempt["exit_code"])
    )
    primary_signal_process = (
        load_signal_process(directory / "online-loading-process.json", attempt)
        if signal_diagnostic else None
    )
    candidates = [(
        "primary-final",
        directory / "macos-online-loading.json",
        directory / "online-loading.log",
        directory / "online-loading-process.json",
    )]
    if signal_diagnostic:
        if attempt.get("diagnostic_retry_attempted") is True:
            candidates.append((
                "lldb-final",
                directory / "lldb/macos-online-loading.json",
                directory / "lldb/online-loading-lldb.log",
                directory / "lldb/online-loading-lldb-process.json",
            ))
        candidates.append((
            "primary-checkpoint",
            directory / "macos-online-loading-checkpoint.json",
            directory / "online-loading.log",
            directory / "online-loading-process.json",
        ))
    rejected: list[str] = []
    for evidence_source, metrics_path, log_path, process_path in candidates:
        if not metrics_path.is_file():
            continue
        try:
            value = validate_metrics_candidate(
                attempt,
                manifest,
                metrics_path=metrics_path,
                log_path=log_path,
                process_path=process_path,
                evidence_source=evidence_source,
                primary_signal_process=primary_signal_process,
            )
        except LoadingError as error:
            rejected.append(f"{evidence_source}: {error}")
            continue
        value["rejected_diagnostic_evidence"] = rejected
        return value
    detail = "; ".join(rejected) if rejected else "no eligible evidence file exists"
    raise LoadingError(f"online-loading attempt has no valid evidence: {detail}")


def diagnostic_observation(value: dict[str, object], manifest: dict[str, object]) -> bool:
    if manifest["runner_class"] != "diagnostic" or value.get("runner_class") != "diagnostic":
        return False
    if value.get("first_visible_ms") is None or integer(
            value.get("max_entity_count"), "max_entity_count", minimum=1) < 1:
        return False
    if value.get("success") is True:
        return True
    bounded = value.get("reason") in ("diagnostic_observation_complete", "first_visible_checkpoint")
    process_bounded = (
        value.get("process_exit_code") == 0 or
        value.get("process_completion_file_observed") is True or
        value.get("diagnostic_signal_evidence") is True or
        (value.get("process_timed_out") is True and value.get("process_sample_succeeded") is True)
    )
    return bounded and process_bounded


def diagnostic_capture(value: dict[str, object], manifest: dict[str, object]) -> bool:
    if manifest["runner_class"] != "diagnostic" or value.get("runner_class") != "diagnostic":
        return False
    if value.get("reason") not in (
            "diagnostic_observation_complete", "visible_timeout", "first_visible_checkpoint"):
        return False
    process_bounded = (
        value.get("process_exit_code") == 0 or
        value.get("process_completion_file_observed") is True or
        value.get("diagnostic_signal_evidence") is True or
        (value.get("process_timed_out") is True and value.get("process_sample_succeeded") is True)
    )
    milestones = value.get("navigation_milestones_ms")
    network_bounded = isinstance(milestones, dict) and milestones.get("domain_connected") is not None and (
        milestones.get("entity_query") is not None or milestones.get("entity_data") is not None
    )
    return process_bounded and network_bounded


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def aggregate(attempts: list[dict[str, object]], metrics: list[dict[str, object]],
              manifest: dict[str, object], minimum_runs: int, failures: list[str]) -> dict[str, object]:
    groups: list[dict[str, object]] = []
    for concurrency in manifest["executed_concurrencies"]:
        for cache_mode in ("cold", "warm"):
            group_attempts = [item for item in attempts if item["concurrency"] == concurrency and
                              item["cache_mode"] == cache_mode]
            group_metrics = [item for item in metrics if item["concurrency"] == concurrency and
                             item["cache_mode"] == cache_mode]
            valid = [item for item in group_metrics if item.get("success") is True and
                     item.get("first_visible_ms") is not None and
                     item.get("snapshot_completed_ms") is not None and
                     item.get("sustained_idle_ms") is not None]
            observed = [item for item in group_metrics if diagnostic_observation(item, manifest)]
            captured = [item for item in group_metrics if diagnostic_capture(item, manifest)]
            bottlenecks = Counter(
                str(item["queue_diagnostics"]["primary_bottleneck"]) for item in group_metrics
            )
            loading_bottlenecks = Counter(
                str(item["queue_diagnostics"]["first_visible_latency_bottleneck"])
                for item in group_metrics
            )
            post_visible_bottlenecks = Counter(
                str(item["queue_diagnostics"]["post_visible_bottleneck"])
                for item in group_metrics
            )
            signals = Counter(
                signal
                for item in group_metrics
                for signal in item["queue_diagnostics"]["bottleneck_signals"]
            )
            evidence_sources = Counter(
                str(item.get("diagnostic_evidence_source", "primary-final"))
                for item in group_metrics
            )
            visible = [finite(item["first_visible_ms"], "first_visible_ms") for item in group_metrics
                       if item.get("first_visible_ms") is not None]
            snapshot = [finite(item["snapshot_completed_ms"], "snapshot_completed_ms") for item in valid]
            idle = [finite(item["sustained_idle_ms"], "sustained_idle_ms") for item in valid]
            groups.append({
                "concurrency": concurrency,
                "cache_mode": cache_mode,
                "attempt_count": len(group_attempts),
                "metrics_count": len(group_metrics),
                "valid_count": len(valid),
                "diagnostic_observation_count": len(observed),
                "diagnostic_capture_count": len(captured),
                "failure_count": sum(not item["accepted"] for item in group_attempts),
                "crash_count": sum(int(item["exit_code"]) in (134, 136, 139) for item in group_attempts),
                "diagnostic_evidence_sources": dict(sorted(evidence_sources.items())),
                "timeout_count": sum(item.get("process_timed_out") is True for item in group_metrics),
                "first_visible_ms_median_partial": median_or_none(visible),
                "snapshot_ms_median": median_or_none(snapshot),
                "sustained_idle_ms_median": median_or_none(idle),
                "dominant_bottleneck": bottlenecks.most_common(1)[0][0] if bottlenecks else None,
                "bottleneck_counts": dict(sorted(bottlenecks.items())),
                "dominant_first_visible_latency_bottleneck": (
                    loading_bottlenecks.most_common(1)[0][0] if loading_bottlenecks else None
                ),
                "first_visible_latency_bottleneck_counts": dict(
                    sorted(loading_bottlenecks.items())
                ),
                "dominant_post_visible_bottleneck": (
                    post_visible_bottlenecks.most_common(1)[0][0]
                    if post_visible_bottlenecks else None
                ),
                "post_visible_bottleneck_counts": dict(sorted(post_visible_bottlenecks.items())),
                "bottleneck_signal_counts": dict(sorted(signals.items())),
                "queue_diagnostics": [item["queue_diagnostics"] for item in group_metrics],
            })
    diagnostic = manifest["runner_class"] == "diagnostic" or manifest.get("translated") is True
    complete = not failures and all(item["valid_count"] >= minimum_runs for item in groups)
    diagnostic_capture_complete = (
        diagnostic and all(item["diagnostic_capture_count"] >= minimum_runs for item in groups)
    )
    diagnostic_visibility_observed = any(item["diagnostic_observation_count"] > 0 for item in groups)
    diagnostic_observation_complete = diagnostic_capture_complete and diagnostic_visibility_observed
    captured_attempts = {
        (int(item["concurrency"]), int(item["run_index"]), str(item["cache_mode"]))
        for item in metrics if diagnostic_capture(item, manifest)
    }
    expected_incomplete = {
        f"c{item['concurrency']}/pair-{item['pair']}/{item['cache_mode']} failed with exit {item['exit_code']}"
        for item in attempts
        if (int(item["concurrency"]), int(item["pair"]), str(item["cache_mode"])) in captured_attempts
        and not item["accepted"]
    }
    hard_failures = [failure for failure in failures if failure not in expected_incomplete]
    if hard_failures:
        diagnostic_observation_complete = False
    warm = [item for item in groups if item["cache_mode"] == "warm" and
            item["valid_count"] >= minimum_runs]
    warm.sort(key=lambda item: (float(item["first_visible_ms_median_partial"]), int(item["concurrency"])))
    observed_best = int(warm[0]["concurrency"]) if warm else None
    decision_ready = (not diagnostic and minimum_runs >= 3 and complete and
                      manifest.get("public_world_informational") is False)
    return {
        "schema_version": 2,
        "platform": "macos",
        "application_sha256": manifest["application_sha256"],
        "location_sha256": manifest["location_sha256"],
        "public_world_informational": True,
        "diagnostic_only": diagnostic,
        "minimum_runs": minimum_runs,
        "attempt_count": len(attempts),
        "metrics_count": len(metrics),
        "measurement_passed": complete,
        "diagnostic_observation_complete": diagnostic_observation_complete,
        "diagnostic_capture_complete": diagnostic_capture_complete,
        "diagnostic_visibility_observed": diagnostic_visibility_observed,
        "decision_ready": decision_ready,
        "selected_concurrency": observed_best if decision_ready else None,
        "observed_best_concurrency": observed_best,
        "bottleneck_summary": {
            f"c{item['concurrency']}-{item['cache_mode']}": item["dominant_bottleneck"]
            for item in groups
        },
        "first_visible_latency_bottleneck_summary": {
            f"c{item['concurrency']}-{item['cache_mode']}":
                item["dominant_first_visible_latency_bottleneck"]
            for item in groups
        },
        "post_visible_bottleneck_summary": {
            f"c{item['concurrency']}-{item['cache_mode']}":
                item["dominant_post_visible_bottleneck"]
            for item in groups
        },
        "passed": complete or diagnostic_observation_complete,
        "groups": groups,
        "failures": hard_failures if diagnostic_observation_complete else failures,
        "incomplete_attempts": sorted(expected_incomplete),
        "limitations": [
            "public world and network are mutable; concurrency observations are informational",
            "--cache isolates resource caches but not the driver-dependent GL shader cache",
            "software-renderer observations may terminate after bounded evidence without a completed frame or idle queues",
        ],
    }


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise LoadingError("refusing to replace a symlinked report")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def write_junit(path: Path, result: dict[str, object]) -> None:
    suite = ET.Element("testsuite", name="overte.macos.online-loading")
    for item in result.get("groups", []):
        case = ET.SubElement(suite, "testcase", classname="overte.macos.online-loading",
                             name=f"c{item['concurrency']}-{item['cache_mode']}")
        if (item["valid_count"] < result.get("minimum_runs", 1) and
                item.get("diagnostic_capture_count", 0) >= result.get("minimum_runs", 1)):
            ET.SubElement(
                case, "skipped",
                message="diagnostic software renderer did not complete full render and idle gates",
            )
        elif item["valid_count"] < result.get("minimum_runs", 1):
            failure = ET.SubElement(case, "failure", message="insufficient valid repetitions")
            failure.text = json.dumps(item, sort_keys=True)
    for index, message in enumerate(result.get("failures", [])):
        case = ET.SubElement(suite, "testcase", classname="overte.macos.online-loading",
                             name=f"attempt-{index + 1}")
        failure = ET.SubElement(case, "failure", message=str(message))
        failure.text = str(message)
    decision = ET.SubElement(suite, "testcase", classname="overte.macos.online-loading",
                             name="download-concurrency-decision")
    if not result.get("decision_ready"):
        ET.SubElement(decision, "skipped", message="controlled native-hardware evidence is unavailable")
    cases = list(suite.findall("testcase"))
    suite.set("tests", str(len(cases)))
    suite.set("failures", str(sum(case.find("failure") is not None for case in cases)))
    suite.set("skipped", str(sum(case.find("skipped") is not None for case in cases)))
    atomic_write(path, ET.tostring(suite, encoding="utf-8", xml_declaration=True) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark_directory", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--minimum-runs", type=int, default=3)
    arguments = parser.parse_args()
    if not 1 <= arguments.minimum_runs <= 20:
        parser.error("--minimum-runs is outside 1..20")
    try:
        manifest = load_manifest(arguments.benchmark_directory)
        if arguments.minimum_runs != manifest["repeats"]:
            raise LoadingError("minimum runs must match the immutable online-loading manifest")
        attempts, failures = load_attempts(arguments.benchmark_directory, manifest)
        metrics = [value for value in
                   (load_metrics(attempt, manifest) for attempt in attempts) if value is not None]
        result = aggregate(attempts, metrics, manifest, arguments.minimum_runs, failures)
        atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
        write_junit(arguments.junit, result)
    except (LoadingError, OSError, KeyError, TypeError, ValueError, statistics.StatisticsError) as error:
        result = {"schema_version": 2, "passed": False, "decision_ready": False,
                  "groups": [], "failures": [str(error)]}
        try:
            atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
            write_junit(arguments.junit, result)
        except (LoadingError, OSError):
            pass
        print(json.dumps(result, sort_keys=True), flush=True)
        return 1
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
