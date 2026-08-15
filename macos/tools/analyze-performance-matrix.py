#!/usr/bin/env python3
"""Validate a fresh macOS graphics matrix and select only evidence-backed profiles."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import tempfile
import xml.etree.ElementTree as ET


class MatrixError(RuntimeError):
    pass


RUN_LABEL = re.compile(r"run-([1-9][0-9]*)\Z")
DIAGNOSTIC_RENDERER_TOKENS = (
    "software", "paravirtual", "virtual", "swiftshader", "llvmpipe", "softpipe", "offscreen",
)
PROFILE_FIELDS = (
    "render_method", "shadows", "haze", "bloom", "ambient_occlusion", "local_lighting",
    "procedural_materials", "antialiasing", "viewport_scale", "forward_samples",
)
STATS_FIELDS = (
    "gpuFrameTime", "batchFrameTime", "engineFrameTime", "drawcalls", "triangles",
    "itemRendered", "shadowRendered", "gpuTextureMemory", "gpuTextureResidentMemory",
    "gpuTextureFramebufferMemory", "texturePendingTransfers",
)
LOD_TIMING_FIELDS = ("present_ms", "engine_ms", "batch_ms", "gpu_ms")


def finite(value: object, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MatrixError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise MatrixError(f"{field} must be finite")
    if minimum is not None and number < minimum:
        raise MatrixError(f"{field} must be at least {minimum}")
    return number


def integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise MatrixError(f"{field} must be an integer >= {minimum}")
    return value


def median_absolute_deviation(values: list[float]) -> float:
    middle = statistics.median(values)
    return statistics.median(abs(value - middle) for value in values)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise MatrixError("refusing to replace a symlinked report")
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


def load_object(path: Path, description: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MatrixError(f"could not read {description}: {error}") from error
    if not isinstance(value, dict):
        raise MatrixError(f"{description} must be a JSON object")
    return value


def load_catalog(path: Path) -> tuple[dict[str, dict[str, object]], dict[str, list[str]], str]:
    payload = load_object(path, "profile catalog")
    if payload.get("schema_version") != 1 or not isinstance(payload.get("profiles"), list):
        raise MatrixError("unsupported profile catalog")
    profiles: dict[str, dict[str, object]] = {}
    quality_scores: set[int] = set()
    for index, profile in enumerate(payload["profiles"]):
        if not isinstance(profile, dict) or not isinstance(profile.get("id"), str):
            raise MatrixError(f"invalid profile catalog entry {index}")
        identifier = profile["id"]
        if identifier in profiles:
            raise MatrixError(f"duplicate profile id {identifier}")
        quality_score = integer(profile.get("quality_score"), f"profile {identifier} quality_score")
        if quality_score in quality_scores:
            raise MatrixError(f"duplicate profile quality score {quality_score}")
        quality_scores.add(quality_score)
        for field in PROFILE_FIELDS:
            if field not in profile:
                raise MatrixError(f"profile {identifier} is missing {field}")
        if profile["render_method"] not in (0, 1):
            raise MatrixError(f"profile {identifier} has invalid render method")
        for field in ("shadows", "haze", "bloom", "ambient_occlusion", "local_lighting",
                      "procedural_materials"):
            if not isinstance(profile[field], bool):
                raise MatrixError(f"profile {identifier} has non-boolean {field}")
        integer(profile["antialiasing"], f"profile {identifier} antialiasing")
        if not 0.1 <= finite(profile["viewport_scale"], f"profile {identifier} viewport_scale") <= 2.0:
            raise MatrixError(f"profile {identifier} viewport scale is outside 0.1..2.0")
        if not 1 <= integer(profile["forward_samples"],
                            f"profile {identifier} forward_samples", minimum=1) <= 32:
            raise MatrixError(f"profile {identifier} forward samples are outside 1..32")
        profiles[identifier] = profile
    orders: dict[str, list[str]] = {}
    for name in ("diagnostic_order", "quick_order", "full_order"):
        order = payload.get(name)
        if not isinstance(order, list) or not order or any(item not in profiles for item in order):
            raise MatrixError(f"invalid {name} in profile catalog")
        if len(set(order)) != len(order):
            raise MatrixError(f"duplicate profile in {name}")
        orders[name] = order
    return profiles, orders, hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(matrix: Path, catalog_hash: str, orders: dict[str, list[str]]) -> dict[str, object]:
    manifest = load_object(matrix / "matrix-manifest.json", "matrix manifest")
    if manifest.get("schema_version") != 1:
        raise MatrixError("unsupported matrix manifest")
    mode = manifest.get("mode")
    runner_class = manifest.get("runner_class")
    fixture_mode = manifest.get("fixture_mode")
    if mode not in ("quick", "full") or runner_class not in ("diagnostic", "hardware"):
        raise MatrixError("invalid matrix mode or runner class")
    expected_fixture = "diagnostic-lite" if runner_class == "diagnostic" else "full"
    if fixture_mode != expected_fixture:
        raise MatrixError("runner class and fixture mode disagree")
    repeats = integer(manifest.get("repeats"), "manifest repeats", minimum=1)
    expected_profiles = manifest.get("expected_profiles")
    expected_order = orders["diagnostic_order" if runner_class == "diagnostic" else f"{mode}_order"]
    if expected_profiles != expected_order:
        raise MatrixError("manifest expected profiles do not match the trusted catalog order")
    if manifest.get("profiles_sha256") != catalog_hash:
        raise MatrixError("profile catalog hash does not match the matrix manifest")
    app_sha = manifest.get("application_sha256")
    if not isinstance(app_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", app_sha):
        raise MatrixError("matrix manifest has no valid application SHA-256")
    return manifest


def load_attempts(matrix: Path, manifest: dict[str, object]) -> tuple[list[dict[str, object]], list[str]]:
    path = matrix / "attempts.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise MatrixError(f"could not read attempt manifest: {error}") from error
    attempts: list[dict[str, object]] = []
    for number, line in enumerate(lines, 1):
        try:
            attempt = json.loads(line)
        except json.JSONDecodeError as error:
            raise MatrixError(f"invalid attempt record {number}: {error}") from error
        if not isinstance(attempt, dict):
            raise MatrixError(f"attempt record {number} must be an object")
        profile = attempt.get("profile")
        label = attempt.get("label")
        result_directory = attempt.get("result_directory")
        if profile not in manifest["expected_profiles"] or not isinstance(label, str):
            raise MatrixError(f"attempt record {number} names an unexpected profile or label")
        if label != "warmup" and not RUN_LABEL.fullmatch(label):
            raise MatrixError(f"attempt record {number} has an unexpected label")
        if not isinstance(result_directory, str):
            raise MatrixError(f"attempt record {number} has no result directory")
        relative = Path(result_directory)
        if relative.is_absolute() or ".." in relative.parts:
            raise MatrixError(f"attempt record {number} escapes the matrix directory")
        attempt["resolved_directory"] = matrix / relative
        integer(attempt.get("run_index"), f"attempt {number} run_index", minimum=1)
        integer(attempt.get("exit_code"), f"attempt {number} exit_code")
        if not isinstance(attempt.get("accepted"), bool):
            raise MatrixError(f"attempt record {number} has invalid acceptance state")
        if attempt["accepted"] != (attempt["exit_code"] == 0):
            raise MatrixError(f"attempt record {number} acceptance and exit status disagree")
        attempts.append(attempt)

    failures: list[str] = []
    expected_repeats = int(manifest["repeats"])
    for profile in manifest["expected_profiles"]:
        warmups = [item for item in attempts if item["profile"] == profile and item["label"] == "warmup"]
        expected_warmups = 1 if manifest["runner_class"] == "hardware" else 0
        if len(warmups) != expected_warmups:
            failures.append(f"{profile}/warmup has {len(warmups)} records instead of {expected_warmups}")
        elif warmups and not warmups[0]["accepted"]:
            failures.append(f"{profile}/warmup failed with exit {warmups[0]['exit_code']}")
        for repeat in range(1, expected_repeats + 1):
            label = f"run-{repeat}"
            matches = [item for item in attempts if item["profile"] == profile and item["label"] == label]
            if len(matches) != 1:
                failures.append(f"{profile}/{label} has {len(matches)} attempt records instead of one")
            elif not matches[0]["accepted"]:
                failures.append(f"{profile}/{label} failed with exit {matches[0]['exit_code']}")
    measured = [item for item in attempts if RUN_LABEL.fullmatch(str(item["label"]))]
    expected_count = len(manifest["expected_profiles"]) * expected_repeats
    if len(measured) != expected_count:
        failures.append(f"matrix has {len(measured)} measured attempts instead of {expected_count}")
    return measured, failures


def validate_distribution(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MatrixError(f"{field} must be an object")
    integer(value.get("count"), f"{field}.count", minimum=1)
    numbers = {
        name: finite(value.get(name), f"{field}.{name}", minimum=0)
        for name in ("mean", "min", "p10", "p50", "p95", "max")
    }
    if not (numbers["min"] <= numbers["p10"] <= numbers["p50"] <=
            numbers["p95"] <= numbers["max"]):
        raise MatrixError(f"{field} percentiles are not monotonic")
    if not numbers["min"] <= numbers["mean"] <= numbers["max"]:
        raise MatrixError(f"{field} mean is outside its observed range")
    return value


def validate_lod_timings(value: object, identifier: str) -> dict[str, object]:
    field = f"{identifier}.lod_timings_ms"
    if not isinstance(value, dict):
        raise MatrixError(f"{field} must be an object")
    if value.get("sampling_interval_ms") != 250 or value.get("semantics") != (
            "polled_latest_and_moving_averages"):
        raise MatrixError(f"{field} has unsupported sampling semantics")
    rows = value.get("raw_samples")
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise MatrixError(f"{field}.raw_samples must contain 1..1000 rows")
    observed: dict[str, list[float]] = {name: [] for name in LOD_TIMING_FIELDS}
    invalid: Counter[str] = Counter()
    previous_elapsed = -1.0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise MatrixError(f"{field}.raw_samples[{index}] must be an object")
        elapsed = finite(row.get("elapsed_ms"), f"{field}.raw_samples[{index}].elapsed_ms")
        if elapsed <= previous_elapsed:
            raise MatrixError(f"{field} sample times are not strictly increasing")
        previous_elapsed = elapsed
        for name in LOD_TIMING_FIELDS:
            sample = row.get(name)
            if sample is None:
                invalid[name] += 1
            else:
                observed[name].append(finite(sample, f"{field}.raw_samples[{index}].{name}", minimum=0))
    for name in LOD_TIMING_FIELDS:
        summary = value.get(name)
        if not isinstance(summary, dict):
            raise MatrixError(f"{field}.{name} must be an object")
        values = observed[name]
        if not values:
            raise MatrixError(f"{field}.{name} has no valid samples")
        validate_distribution(summary, f"{field}.{name}")
        expected = {
            "count": len(values),
            "invalid_count": invalid[name],
            "zero_count": sum(item == 0 for item in values),
            "positive_count": sum(item > 0 for item in values),
        }
        for count_name, count_value in expected.items():
            if integer(summary.get(count_name), f"{field}.{name}.{count_name}") != count_value:
                raise MatrixError(f"{field}.{name}.{count_name} is inconsistent")
        if summary.get("available") is not True:
            raise MatrixError(f"{field}.{name} must report available samples")
        sorted_values = sorted(values)
        recomputed = {
            "mean": statistics.fmean(values),
            "min": sorted_values[0],
            "p10": percentile(sorted_values, 0.10),
            "p50": percentile(sorted_values, 0.50),
            "p95": percentile(sorted_values, 0.95),
            "max": sorted_values[-1],
        }
        for metric, expected_value in recomputed.items():
            actual = finite(summary.get(metric), f"{field}.{name}.{metric}", minimum=0)
            if not math.isclose(actual, expected_value, rel_tol=1e-9, abs_tol=1e-6):
                raise MatrixError(f"{field}.{name}.{metric} is inconsistent")
    return value


def bottleneck_classification(run: dict[str, object]) -> dict[str, object]:
    timings = run["lod_timings_ms"]
    present = float(timings["present_ms"]["p95"])
    engine = float(timings["engine_ms"]["p95"])
    batch = float(timings["batch_ms"]["p95"])
    gpu = float(timings["gpu_ms"]["p95"])
    submit = float(run["p95_frame_ms"])
    if gpu > 0 and gpu >= max(16.67, engine * 1.25):
        primary = "gpu"
    elif engine >= max(16.67, gpu * 1.25):
        primary = "cpu-engine"
    elif submit >= max(16.67, engine * 1.25, gpu * 1.25):
        primary = "cpu-submit"
    elif present >= max(20.0, engine * 1.25, gpu * 1.25):
        primary = "present-or-pacing"
    else:
        primary = "balanced-or-refresh-limited"
    return {
        "primary": primary,
        "p95_ms": {
            "render_submit": submit,
            "present": present,
            "engine": engine,
            "batch": batch,
            "gpu": gpu,
        },
        "gpu_to_engine_ratio": None if engine == 0 else gpu / engine,
        "frame_budget_60hz_ms": 16.67,
    }


def load_run(attempt: dict[str, object], manifest: dict[str, object],
             catalog: dict[str, dict[str, object]]) -> dict[str, object]:
    directory = attempt["resolved_directory"]
    marker = directory / "profile-accepted"
    if not marker.is_file():
        raise MatrixError(f"accepted attempt {attempt['profile']}/{attempt['label']} has no marker")
    payload = load_object(directory / "macos-profile.json", "profile result")
    identifier = str(attempt["profile"])
    if payload.get("schema_version") != 2 or payload.get("platform") != "macos":
        raise MatrixError(f"unsupported profile result for {identifier}/{attempt['label']}")
    if payload.get("profile_id") != identifier or payload.get("fixture_mode") != manifest["fixture_mode"]:
        raise MatrixError(f"profile identity or fixture mode mismatch for {identifier}/{attempt['label']}")
    if payload.get("run_index") != attempt["run_index"] or payload.get("measurement_complete") is not True:
        raise MatrixError(f"incomplete or mismatched run index for {identifier}/{attempt['label']}")
    trusted = catalog[identifier]
    if payload.get("quality_score") != trusted["quality_score"] or payload.get("requested_profile") != trusted:
        raise MatrixError(f"profile {identifier} does not match the trusted catalog")
    actual = payload.get("actual_profile")
    if not isinstance(actual, dict) or any(actual.get(field) != trusted[field] for field in PROFILE_FIELDS):
        raise MatrixError(f"profile {identifier} did not apply the requested settings")
    platform_info = payload.get("platform_info")
    if not isinstance(platform_info, dict):
        raise MatrixError(f"profile {identifier} is missing platform information")
    if trusted["render_method"] == 0 and platform_info.get("deferred_capable") is not True:
        raise MatrixError(f"profile {identifier} requested deferred rendering on an incapable GPU")

    samples_value = payload.get("samples_us")
    if not isinstance(samples_value, list) or not samples_value:
        raise MatrixError(f"profile {identifier} has no frame samples")
    samples = [finite(value, f"{identifier}.samples_us", minimum=0.000001) for value in samples_value]
    if integer(payload.get("sample_count"), f"{identifier}.sample_count", minimum=1) != len(samples):
        raise MatrixError(f"profile {identifier} sample count is inconsistent")
    reported_p95 = finite(payload.get("p95_frame_ms"), f"{identifier}.p95_frame_ms", minimum=0)
    reported_p99 = finite(payload.get("p99_frame_ms"), f"{identifier}.p99_frame_ms", minimum=0)
    if not math.isclose(reported_p95, percentile(samples, 0.95) / 1000.0, abs_tol=1e-6):
        raise MatrixError(f"profile {identifier} has a forged or stale p95")
    if not math.isclose(reported_p99, percentile(samples, 0.99) / 1000.0, abs_tol=1e-6):
        raise MatrixError(f"profile {identifier} has a forged or stale p99")
    for field in ("over_16_67_ms", "over_33_33_ms"):
        integer(payload.get(field), f"{identifier}.{field}")
    rates = payload.get("rates_hz")
    if not isinstance(rates, dict):
        raise MatrixError(f"profile {identifier} has no rate distributions")
    for name in ("render", "present", "new_frame", "dropped", "simulation"):
        validate_distribution(rates.get(name), f"{identifier}.rates_hz.{name}")
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        raise MatrixError(f"profile {identifier} has no render statistics")
    for name in STATS_FIELDS:
        validate_distribution(stats.get(name), f"{identifier}.stats.{name}")
    payload["lod_timings_ms"] = validate_lod_timings(payload.get("lod_timings_ms"), identifier)
    payload["bottleneck"] = bottleneck_classification(payload)
    return payload


def renderer_name(payload: dict[str, object]) -> str:
    info = payload.get("platform_info")
    gpu = info.get("gpu") if isinstance(info, dict) else None
    if isinstance(gpu, dict):
        for key in ("model", "name", "description"):
            if isinstance(gpu.get(key), str) and gpu[key].strip():
                return gpu[key].strip()
    platform = info.get("platform") if isinstance(info, dict) else None
    graphics_apis = platform.get("graphicsAPIs") if isinstance(platform, dict) else None
    if isinstance(graphics_apis, list):
        for api in graphics_apis:
            if isinstance(api, dict) and isinstance(api.get("renderer"), str) and api["renderer"].strip():
                return api["renderer"].strip()
    return "unknown"


def hardware_key(payload: dict[str, object], manifest: dict[str, object]) -> str:
    info = payload.get("platform_info")
    fragments = [str(manifest["machine"]), str(manifest["application_sha256"])]
    if isinstance(info, dict):
        for section_name in ("computer", "cpu", "gpu", "display", "platform"):
            section = info.get(section_name)
            if isinstance(section, dict):
                fragments.append(json.dumps(section, sort_keys=True, separators=(",", ":")))
    return "|".join(fragments)


def evidence_class(payload: dict[str, object], manifest: dict[str, object]) -> str:
    renderer = renderer_name(payload).lower()
    if (manifest["runner_class"] == "diagnostic" or manifest.get("translated") is True or
            renderer == "unknown" or
            any(token in renderer for token in DIAGNOSTIC_RENDERER_TOKENS)):
        return "diagnostic-software"
    machine = str(manifest.get("machine", "unknown"))
    if machine == "arm64" and "apple" in renderer:
        return "apple-silicon-native"
    return "mac-hardware-other"


def run_contract(run: dict[str, object], target: int) -> bool:
    rates = run["rates_hz"]
    count = int(run["sample_count"])
    jank_ratio = int(run["over_33_33_ms"]) / count
    if target == 60:
        return (
            float(rates["present"]["p10"]) >= 55.0
            and float(rates["present"]["p50"]) >= 58.0
            and float(rates["new_frame"]["p10"]) >= 50.0
            and float(rates["new_frame"]["p50"]) >= 55.0
            and float(rates["dropped"]["p95"]) <= 0.5
            and float(run["p95_frame_ms"]) <= 18.0
            and float(run["p99_frame_ms"]) <= 25.0
            and jank_ratio <= 0.005
        )
    return (
        float(rates["present"]["p10"]) >= 27.0
        and float(rates["present"]["p50"]) >= 29.0
        and float(rates["new_frame"]["p10"]) >= 25.0
        and float(rates["new_frame"]["p50"]) >= 27.0
        and float(rates["dropped"]["p95"]) <= 0.5
        and float(run["p95_frame_ms"]) <= 35.0
        and float(run["p99_frame_ms"]) <= 45.0
        and jank_ratio <= 0.005
    )


def aggregate(runs: list[dict[str, object]], manifest: dict[str, object],
              minimum_runs: int, attempt_failures: list[str]) -> dict[str, object]:
    if not runs and not attempt_failures:
        raise MatrixError("no accepted profile results found")
    hardware_keys = {hardware_key(run, manifest) for run in runs}
    fixture_versions = {run.get("fixture_version") for run in runs}
    fixture_modes = {run.get("fixture_mode") for run in runs}
    evidence_classes = {evidence_class(run, manifest) for run in runs}
    if len(hardware_keys) > 1 or len(fixture_versions) > 1 or len(fixture_modes) > 1:
        raise MatrixError("profile results mix hardware, fixture versions, or fixture modes")
    if len(evidence_classes) > 1:
        raise MatrixError("profile results mix incompatible evidence classes")
    evidence = next(iter(evidence_classes), "diagnostic-unknown")
    if manifest["runner_class"] == "hardware" and evidence == "diagnostic-software":
        raise MatrixError("hardware matrix produced software or virtual renderer evidence")

    by_profile: dict[str, list[dict[str, object]]] = {
        profile: [] for profile in manifest["expected_profiles"]
    }
    for run in runs:
        by_profile[str(run["profile_id"])].append(run)
    profiles: list[dict[str, object]] = []
    for identifier in manifest["expected_profiles"]:
        profile_runs = by_profile[identifier]
        p95 = [float(run["p95_frame_ms"]) for run in profile_runs]
        p99 = [float(run["p99_frame_ms"]) for run in profile_runs]
        present = [float(run["rates_hz"]["present"]["p50"]) for run in profile_runs]
        new_frame = [float(run["rates_hz"]["new_frame"]["p50"]) for run in profile_runs]
        enough = len(profile_runs) >= minimum_runs
        stable_60 = enough and all(run_contract(run, 60) for run in profile_runs)
        stable_30 = enough and all(run_contract(run, 30) for run in profile_runs)
        bottlenecks = Counter(str(run["bottleneck"]["primary"]) for run in profile_runs)
        dominant_bottleneck = bottlenecks.most_common(1)[0][0] if bottlenecks else None
        lod_medians = {
            name: statistics.median(float(run["lod_timings_ms"][name]["p95"])
                                    for run in profile_runs) if profile_runs else None
            for name in LOD_TIMING_FIELDS
        }
        profiles.append({
            "profile_id": identifier,
            "quality_score": int(profile_runs[0]["quality_score"]) if profile_runs else None,
            "run_count": len(profile_runs),
            "enough_runs": enough,
            "all_runs_60hz": stable_60,
            "all_runs_30hz": stable_30,
            "p95_frame_ms_median": statistics.median(p95) if p95 else None,
            "p95_frame_ms_mad": median_absolute_deviation(p95) if p95 else None,
            "p99_frame_ms_max": max(p99) if p99 else None,
            "present_hz_median": statistics.median(present) if present else None,
            "present_hz_minimum": min(present) if present else None,
            "present_hz_mad": median_absolute_deviation(present) if present else None,
            "new_frame_hz_median": statistics.median(new_frame) if new_frame else None,
            "run_indices": sorted(int(run["run_index"]) for run in profile_runs),
            "requested_profile": profile_runs[0].get("requested_profile") if profile_runs else None,
            "dominant_bottleneck": dominant_bottleneck,
            "bottleneck_counts": dict(sorted(bottlenecks.items())),
            "lod_timing_p95_ms_median": lod_medians,
        })

    diagnostic_only = evidence.startswith("diagnostic")
    evidence_complete = not attempt_failures and all(item["enough_runs"] for item in profiles)
    decision_ready = (
        not diagnostic_only and manifest["mode"] == "full" and int(manifest["repeats"]) >= 3
        and minimum_runs >= 3 and evidence_complete
    )
    stable_60 = [item for item in profiles if item["all_runs_60hz"]]
    stable_30 = [item for item in profiles if item["all_runs_30hz"]]
    order = lambda item: (int(item["quality_score"]), float(item["present_hz_median"]))
    stable_60.sort(key=order, reverse=True)
    stable_30.sort(key=order, reverse=True)
    provisional = stable_60[0]["profile_id"] if stable_60 else None
    fallback = stable_30[0]["profile_id"] if stable_30 else None
    selected = provisional if decision_ready else None
    diagnostic_profile = None
    if diagnostic_only:
        measured = [item for item in profiles if item["enough_runs"]]
        measured.sort(key=order, reverse=True)
        diagnostic_profile = measured[0]["profile_id"] if measured else None
        provisional = None
        fallback = None
    passed = evidence_complete and (not decision_ready or selected is not None)
    limitations = []
    if diagnostic_only:
        limitations.append("software or virtual renderer evidence cannot certify gameplay quality")
    if not decision_ready:
        limitations.append("profile selection requires a full matrix with at least three native-hardware runs")
    return {
        "schema_version": 2,
        "platform": "macos",
        "matrix_mode": manifest["mode"],
        "fixture_version": next(iter(fixture_versions), None),
        "fixture_mode": manifest["fixture_mode"],
        "application_sha256": manifest["application_sha256"],
        "profiles_sha256": manifest["profiles_sha256"],
        "hardware_key": next(iter(hardware_keys), "unknown"),
        "renderer": renderer_name(runs[0]) if runs else "unknown",
        "evidence_class": evidence,
        "diagnostic_only": diagnostic_only,
        "certification": "diagnostic-only" if diagnostic_only else ("decision-ready" if decision_ready else "provisional"),
        "minimum_runs": minimum_runs,
        "decision_ready": decision_ready,
        "measurement_passed": evidence_complete,
        "selected_profile": selected,
        "provisional_profile": provisional,
        "fallback_profile_30hz": fallback,
        "diagnostic_profile": diagnostic_profile,
        "bottleneck_summary": {
            str(item["profile_id"]): item["dominant_bottleneck"] for item in profiles
        },
        "passed": passed,
        "profiles": profiles,
        "failures": attempt_failures,
        "limitations": limitations,
    }


def write_junit(path: Path, result: dict[str, object]) -> None:
    profiles = result.get("profiles", [])
    failures = list(result.get("failures", []))
    suite = ET.Element("testsuite", name="overte.macos.performance-matrix")
    for item in profiles:
        case = ET.SubElement(suite, "testcase", classname="overte.macos.performance",
                             name=str(item["profile_id"]))
        if not item.get("enough_runs"):
            failure = ET.SubElement(case, "failure", message="missing accepted measurements")
            failure.text = json.dumps(item, sort_keys=True)
        elif not item.get("all_runs_30hz"):
            ET.SubElement(case, "skipped", message="measured profile did not meet the 30 Hz fallback contract")
    for index, message in enumerate(failures):
        case = ET.SubElement(suite, "testcase", classname="overte.macos.performance",
                             name=f"infrastructure-{index + 1}")
        failure = ET.SubElement(case, "failure", message=str(message))
        failure.text = str(message)
    decision = ET.SubElement(suite, "testcase", classname="overte.macos.performance",
                             name="quality-profile-decision")
    if not result.get("decision_ready"):
        ET.SubElement(decision, "skipped", message="full native-hardware three-run evidence is not available")
    elif result.get("selected_profile") is None:
        ET.SubElement(decision, "failure", message="no profile met the 60 Hz gameplay contract")
    cases = list(suite.findall("testcase"))
    suite.set("tests", str(len(cases)))
    suite.set("failures", str(sum(case.find("failure") is not None for case in cases)))
    suite.set("skipped", str(sum(case.find("skipped") is not None for case in cases)))
    atomic_write(path, ET.tostring(suite, encoding="utf-8", xml_declaration=True) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix_directory", type=Path)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--minimum-runs", type=int, default=3)
    arguments = parser.parse_args()
    if not 1 <= arguments.minimum_runs <= 20:
        parser.error("--minimum-runs is outside 1..20")
    try:
        catalog, orders, catalog_hash = load_catalog(arguments.profiles)
        manifest = load_manifest(arguments.matrix_directory, catalog_hash, orders)
        if arguments.minimum_runs != int(manifest["repeats"]):
            raise MatrixError("minimum runs must match the immutable matrix manifest")
        attempts, attempt_failures = load_attempts(arguments.matrix_directory, manifest)
        runs = [load_run(attempt, manifest, catalog) for attempt in attempts if attempt["accepted"]]
        result = aggregate(runs, manifest, arguments.minimum_runs, attempt_failures)
        atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
        write_junit(arguments.junit, result)
    except (MatrixError, OSError, KeyError, TypeError, ValueError, statistics.StatisticsError) as error:
        result = {
            "schema_version": 2,
            "passed": False,
            "decision_ready": False,
            "profiles": [],
            "failures": [str(error)],
        }
        try:
            atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
            write_junit(arguments.junit, result)
        except (MatrixError, OSError):
            pass
        print(json.dumps(result, sort_keys=True), flush=True)
        return 1
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
