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
    milestones = value.get("host_milestones_ms")
    milestones = milestones if isinstance(milestones, dict) else {}

    def delta(start: str, end: str) -> float | None:
        left, right = milestones.get(start), milestones.get(end)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)) and right >= left:
            return round(float(right) - float(left), 3)
        return None

    last = samples[-1]
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
        "query_to_data_ms": delta("entity_query", "entity_data"),
        "data_to_handoff_ms": delta("entity_data", "render_handoff"),
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

    if milestones.get("domain_connected") is None:
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
    diagnostics["bottleneck_signals"] = signals
    return diagnostics


def load_manifest(root: Path) -> dict[str, object]:
    manifest = load_object(root / "online-loading-manifest.json", "online-loading manifest")
    if manifest.get("schema_version") != 1 or manifest.get("runner_class") not in ("diagnostic", "hardware"):
        raise LoadingError("unsupported online-loading manifest")
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
        exit_code = integer(attempt.get("exit_code"), f"attempt {number} exit_code")
        if not isinstance(attempt.get("accepted"), bool) or not isinstance(attempt.get("metrics_present"), bool):
            raise LoadingError(f"online attempt record {number} has invalid evidence flags")
        if attempt["accepted"] != (exit_code == 0):
            raise LoadingError(f"online attempt record {number} acceptance and exit status disagree")
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


def load_metrics(attempt: dict[str, object], manifest: dict[str, object]) -> dict[str, object] | None:
    directory = attempt["resolved_directory"]
    if not attempt["metrics_present"]:
        return None
    payload = load_object(directory / "macos-online-loading.json", "online-loading metrics")
    if payload.get("schema_version") != 1 or payload.get("platform") != "macos":
        raise LoadingError("unsupported online-loading result")
    if (payload.get("cache_mode") != attempt["cache_mode"] or
            payload.get("concurrency") != attempt["concurrency"] or
            payload.get("run_index") != attempt["pair"]):
        raise LoadingError("online-loading result does not match its attempt")
    if payload.get("runner_class") != manifest["runner_class"]:
        raise LoadingError("online-loading result runner class does not match its manifest")
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
    payload["host_milestones_ms"] = log_milestones(directory / "online-loading.log")
    process = load_object(directory / "online-loading-process.json", "online-loading process result")
    payload["process_exit_code"] = process.get("exit_code")
    payload["process_timed_out"] = process.get("timed_out") is True
    payload["process_sample_succeeded"] = process.get("sample_succeeded") is True
    payload["process_completion_file_observed"] = process.get("completion_file_observed") is True
    payload["queue_diagnostics"] = queue_diagnostics(payload)
    return payload


def diagnostic_observation(value: dict[str, object], manifest: dict[str, object]) -> bool:
    if manifest["runner_class"] != "diagnostic" or value.get("runner_class") != "diagnostic":
        return False
    if value.get("first_visible_ms") is None or integer(
            value.get("max_entity_count"), "max_entity_count", minimum=1) < 1:
        return False
    if value.get("success") is True:
        return True
    bounded = value.get("reason") == "diagnostic_observation_complete"
    process_bounded = (
        value.get("process_exit_code") == 0 or
        value.get("process_completion_file_observed") is True or
        (value.get("process_timed_out") is True and value.get("process_sample_succeeded") is True)
    )
    return bounded and process_bounded


def diagnostic_capture(value: dict[str, object], manifest: dict[str, object]) -> bool:
    if manifest["runner_class"] != "diagnostic" or value.get("runner_class") != "diagnostic":
        return False
    if value.get("reason") not in ("diagnostic_observation_complete", "visible_timeout"):
        return False
    process_bounded = (
        value.get("process_exit_code") == 0 or
        value.get("process_completion_file_observed") is True or
        (value.get("process_timed_out") is True and value.get("process_sample_succeeded") is True)
    )
    milestones = value.get("host_milestones_ms")
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
            signals = Counter(
                signal
                for item in group_metrics
                for signal in item["queue_diagnostics"]["bottleneck_signals"]
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
                "timeout_count": sum(item.get("process_timed_out") is True for item in group_metrics),
                "first_visible_ms_median_partial": median_or_none(visible),
                "snapshot_ms_median": median_or_none(snapshot),
                "sustained_idle_ms_median": median_or_none(idle),
                "dominant_bottleneck": bottlenecks.most_common(1)[0][0] if bottlenecks else None,
                "bottleneck_counts": dict(sorted(bottlenecks.items())),
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
