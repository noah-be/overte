#!/usr/bin/env python3
"""Validate repeated cold/warm macOS online world-loading measurements."""

from __future__ import annotations

import argparse
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


class LoadingError(RuntimeError):
    pass


def finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LoadingError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise LoadingError(f"{name} must be finite")
    return number


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


def load_attempt(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LoadingError(f"could not read {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise LoadingError(f"unsupported online-loading result in {path}")
    if payload.get("platform") != "macos" or payload.get("cache_mode") not in ("cold", "warm"):
        raise LoadingError(f"invalid platform/cache mode in {path}")
    samples = payload.get("queue_samples")
    if not isinstance(samples, list) or not samples or len(samples) > 1000:
        raise LoadingError(f"invalid queue samples in {path}")
    elapsed_values: list[float] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise LoadingError(f"queue sample {index} is not an object")
        elapsed = finite(sample.get("elapsed_ms"), f"queue_samples[{index}].elapsed_ms")
        if elapsed_values and elapsed <= elapsed_values[-1]:
            raise LoadingError(f"queue sample times are not strictly increasing in {path}")
        elapsed_values.append(elapsed)
        for key in ("downloads", "downloads_pending", "processing", "processing_pending",
                    "texture_pending_mb", "entity_count", "visible_count", "present_hz", "new_frame_hz"):
            if finite(sample.get(key), f"queue_samples[{index}].{key}") < 0:
                raise LoadingError(f"negative queue metric {key} in {path}")
    for name in ("first_entities_ms", "first_visible_ms", "snapshot_completed_ms"):
        value = payload.get(name)
        if value is not None:
            finite(value, name)
    payload["host_milestones_ms"] = log_milestones(path.with_name("online-loading.log"))
    payload["result_path"] = str(path.relative_to(path.parents[3]))
    return payload


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def aggregate(attempts: list[dict[str, object]], minimum_runs: int) -> dict[str, object]:
    groups: dict[tuple[int, str], list[dict[str, object]]] = {}
    for attempt in attempts:
        key = (int(attempt["concurrency"]), str(attempt["cache_mode"]))
        groups.setdefault(key, []).append(attempt)
    summaries: list[dict[str, object]] = []
    failures: list[str] = []
    for (concurrency, cache_mode), group in sorted(groups.items()):
        valid = [item for item in group if item.get("success") is True and
                 item.get("first_visible_ms") is not None and item.get("snapshot_completed_ms") is not None]
        if len(valid) < minimum_runs:
            failures.append(f"concurrency {concurrency} {cache_mode} has only {len(valid)} valid runs")
        first_visible = [finite(item["first_visible_ms"], "first_visible_ms") for item in valid]
        snapshot = [finite(item["snapshot_completed_ms"], "snapshot_completed_ms") for item in valid]
        idle = [finite(item["sustained_idle_ms"], "sustained_idle_ms") for item in valid
                if item.get("sustained_idle_ms") is not None]
        summaries.append({
            "concurrency": concurrency,
            "cache_mode": cache_mode,
            "attempt_count": len(group),
            "valid_count": len(valid),
            "first_visible_ms_median": median_or_none(first_visible),
            "snapshot_ms_median": median_or_none(snapshot),
            "sustained_idle_ms_median": median_or_none(idle),
            "idle_completion_rate": len(idle) / len(valid) if valid else 0,
        })
    candidates: list[dict[str, object]] = []
    for summary in summaries:
        if summary["cache_mode"] == "warm" and summary["valid_count"] >= minimum_runs:
            candidates.append(summary)
    candidates.sort(key=lambda item: (float(item["first_visible_ms_median"]), int(item["concurrency"])))
    selected_concurrency = int(candidates[0]["concurrency"]) if candidates else None
    return {
        "schema_version": 1,
        "platform": "macos",
        "public_world_informational": True,
        "minimum_runs": minimum_runs,
        "attempt_count": len(attempts),
        "selected_concurrency": selected_concurrency,
        "passed": not failures and selected_concurrency is not None,
        "groups": summaries,
        "failures": failures,
        "limitations": [
            "public world and network are mutable; comparisons are informational",
            "--cache isolates resource caches but not the driver-dependent GL shader cache",
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
    groups = result.get("groups", [])
    infrastructure_failures = result.get("failures", []) if not groups else []
    failures = sum(item["valid_count"] < result.get("minimum_runs", 1) for item in groups)
    failures += len(infrastructure_failures)
    suite = ET.Element("testsuite", name="overte.macos.online-loading",
                       tests=str(len(groups) + len(infrastructure_failures)), failures=str(failures))
    for item in groups:
        case = ET.SubElement(suite, "testcase", classname="overte.macos.online-loading",
                             name=f"c{item['concurrency']}-{item['cache_mode']}")
        if item["valid_count"] < result.get("minimum_runs", 1):
            ET.SubElement(case, "failure", message="insufficient valid repetitions")
    for index, message in enumerate(infrastructure_failures):
        case = ET.SubElement(suite, "testcase", classname="overte.macos.online-loading",
                             name=f"infrastructure-{index + 1}")
        failure = ET.SubElement(case, "failure", message=str(message))
        failure.text = str(message)
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
        markers = sorted(arguments.benchmark_directory.glob("c*/pair-*/cold/online-loading-accepted"))
        markers += sorted(arguments.benchmark_directory.glob("c*/pair-*/warm/online-loading-accepted"))
        paths = [marker.with_name("macos-online-loading.json") for marker in markers]
        attempts = [load_attempt(path) for path in paths]
        if not attempts:
            raise LoadingError("no online-loading results found")
        result = aggregate(attempts, arguments.minimum_runs)
        atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
        write_junit(arguments.junit, result)
    except (LoadingError, OSError, statistics.StatisticsError) as error:
        result = {"schema_version": 1, "passed": False, "groups": [], "failures": [str(error)]}
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
