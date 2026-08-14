#!/usr/bin/env python3
"""Aggregate repeated macOS graphics profiles and select a Pareto candidate."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import xml.etree.ElementTree as ET


class MatrixError(RuntimeError):
    pass


def finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MatrixError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise MatrixError(f"{field} must be finite")
    return number


def median_absolute_deviation(values: list[float]) -> float:
    middle = statistics.median(values)
    return statistics.median(abs(value - middle) for value in values)


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


def load_run(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MatrixError(f"could not read {path.name}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise MatrixError(f"unsupported profile result in {path}")
    if payload.get("platform") != "macos":
        raise MatrixError(f"non-macOS profile result in {path}")
    if not isinstance(payload.get("profile_id"), str):
        raise MatrixError(f"missing profile id in {path}")
    rates = payload.get("rates_hz")
    if not isinstance(rates, dict) or not isinstance(rates.get("present"), dict):
        raise MatrixError(f"missing present-rate distribution in {path}")
    samples = payload.get("samples_us")
    if not isinstance(samples, list) or len(samples) != payload.get("sample_count"):
        raise MatrixError(f"invalid raw frame samples in {path}")
    finite(payload.get("p95_frame_ms"), "p95_frame_ms")
    finite(rates["present"].get("p50"), "rates_hz.present.p50")
    return payload


def renderer_name(payload: dict[str, object]) -> str:
    info = payload.get("platform_info")
    if not isinstance(info, dict):
        return "unknown"
    gpu = info.get("gpu")
    if not isinstance(gpu, dict):
        return "unknown"
    for key in ("model", "name", "description"):
        if isinstance(gpu.get(key), str) and gpu[key]:
            return gpu[key]
    return "unknown"


def hardware_key(payload: dict[str, object]) -> str:
    info = payload.get("platform_info")
    if not isinstance(info, dict):
        return "unknown"
    fragments: list[str] = []
    for section_name in ("computer", "cpu", "gpu", "display"):
        section = info.get(section_name)
        if isinstance(section, dict):
            fragments.append(json.dumps(section, sort_keys=True, separators=(",", ":")))
    return "|".join(fragments) or "unknown"


def aggregate(runs: list[dict[str, object]], minimum_runs: int) -> dict[str, object]:
    by_profile: dict[str, list[dict[str, object]]] = {}
    hardware_keys = {hardware_key(run) for run in runs}
    fixture_versions = {run.get("fixture_version") for run in runs}
    if len(hardware_keys) != 1:
        raise MatrixError("profile results mix different hardware fingerprints")
    if len(fixture_versions) != 1:
        raise MatrixError("profile results mix different fixture versions")
    for run in runs:
        by_profile.setdefault(str(run["profile_id"]), []).append(run)

    profiles: list[dict[str, object]] = []
    for identifier, profile_runs in sorted(by_profile.items()):
        p95 = [finite(run["p95_frame_ms"], "p95_frame_ms") for run in profile_runs]
        present = [finite(run["rates_hz"]["present"]["p50"], "present.p50") for run in profile_runs]
        new_frame = [finite(run["rates_hz"]["new_frame"]["p50"], "new_frame.p50") for run in profile_runs]
        quality_scores = {int(run["quality_score"]) for run in profile_runs}
        if len(quality_scores) != 1:
            raise MatrixError(f"profile {identifier} has inconsistent quality scores")
        profiles.append({
            "profile_id": identifier,
            "quality_score": quality_scores.pop(),
            "run_count": len(profile_runs),
            "enough_runs": len(profile_runs) >= minimum_runs,
            "p95_frame_ms_median": statistics.median(p95),
            "p95_frame_ms_mad": median_absolute_deviation(p95),
            "present_hz_median": statistics.median(present),
            "present_hz_mad": median_absolute_deviation(present),
            "new_frame_hz_median": statistics.median(new_frame),
            "run_indices": sorted(int(run["run_index"]) for run in profile_runs),
            "requested_profile": profile_runs[0].get("requested_profile"),
        })

    if not profiles:
        raise MatrixError("no valid profile results found")
    renderer = renderer_name(runs[0])
    diagnostic_only = any(token in renderer.lower() for token in ("software", "paravirtual", "llvmpipe"))
    maximum_present = max(float(item["present_hz_median"]) for item in profiles)
    for item in profiles:
        enough = bool(item["enough_runs"])
        if diagnostic_only:
            item["stable"] = enough and float(item["present_hz_median"]) >= max(0.25, maximum_present * 0.70)
            item["stability_contract"] = "diagnostic-relative-70pct"
            item["target_hz"] = None
        else:
            stable_60 = (
                enough
                and float(item["present_hz_median"]) >= 58.0
                and float(item["new_frame_hz_median"]) >= 55.0
                and float(item["p95_frame_ms_median"]) <= 18.0
            )
            stable_30 = (
                enough
                and float(item["present_hz_median"]) >= 29.0
                and float(item["new_frame_hz_median"]) >= 27.0
                and float(item["p95_frame_ms_median"]) <= 35.0
            )
            item["stable"] = stable_60 or stable_30
            item["target_hz"] = 60 if stable_60 else (30 if stable_30 else None)
            item["stability_contract"] = "interactive-60hz" if stable_60 else "interactive-30hz-fallback"

    candidates = [item for item in profiles if item["stable"]]
    if not diagnostic_only and any(item["target_hz"] == 60 for item in candidates):
        candidates = [item for item in candidates if item["target_hz"] == 60]
    candidates.sort(key=lambda item: (int(item["quality_score"]), float(item["present_hz_median"])), reverse=True)
    selected = candidates[0]["profile_id"] if candidates else None
    return {
        "schema_version": 1,
        "platform": "macos",
        "fixture_version": next(iter(fixture_versions)),
        "hardware_key": next(iter(hardware_keys)),
        "renderer": renderer,
        "diagnostic_only": diagnostic_only,
        "minimum_runs": minimum_runs,
        "profile_count": len(profiles),
        "selected_profile": selected,
        "passed": selected is not None,
        "profiles": profiles,
        "limitations": (["software renderer results do not certify real Mac gameplay"] if diagnostic_only else []),
    }


def write_junit(path: Path, result: dict[str, object]) -> None:
    profiles = result.get("profiles", [])
    failures = sum(not item["stable"] for item in profiles)
    suite = ET.Element(
        "testsuite",
        name="overte.macos.performance-matrix",
        tests=str(len(profiles)),
        failures=str(failures),
    )
    for item in profiles:
        case = ET.SubElement(
            suite,
            "testcase",
            classname="overte.macos.performance",
            name=str(item["profile_id"]),
        )
        if not item["stable"]:
            failure = ET.SubElement(case, "failure", message="profile did not meet stability contract")
            failure.text = json.dumps(item, sort_keys=True)
    atomic_write(path, ET.tostring(suite, encoding="utf-8", xml_declaration=True) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix_directory", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--minimum-runs", type=int, default=3)
    arguments = parser.parse_args()
    if arguments.minimum_runs <= 0 or arguments.minimum_runs > 20:
        parser.error("--minimum-runs is outside 1..20")
    try:
        paths = sorted(arguments.matrix_directory.glob("*/run-*/macos-profile.json"))
        runs = [load_run(path) for path in paths]
        result = aggregate(runs, arguments.minimum_runs)
        atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
        write_junit(arguments.junit, result)
    except (MatrixError, OSError, statistics.StatisticsError) as error:
        result = {"schema_version": 1, "passed": False, "failures": [str(error)]}
        try:
            atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
            write_junit(arguments.junit, {"profiles": []})
        except (MatrixError, OSError):
            pass
        print(json.dumps(result, sort_keys=True), flush=True)
        return 1
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
