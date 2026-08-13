#!/usr/bin/env python3
"""Validate and summarize an Overte macOS frame-timing result."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET


MAX_SAMPLES = 100_000
REPORTED_FIELDS = {
    "mean_frame_ms": lambda values: sum(values) / len(values) / 1000.0,
    "min_frame_ms": lambda values: values[0] / 1000.0,
    "p50_frame_ms": lambda values: percentile(values, 0.50) / 1000.0,
    "p90_frame_ms": lambda values: percentile(values, 0.90) / 1000.0,
    "p95_frame_ms": lambda values: percentile(values, 0.95) / 1000.0,
    "p99_frame_ms": lambda values: percentile(values, 0.99) / 1000.0,
    "max_frame_ms": lambda values: values[-1] / 1000.0,
}


class PerformanceError(RuntimeError):
    pass


def percentile(sorted_values: list[float], fraction: float) -> float:
    return sorted_values[max(0, math.ceil(len(sorted_values) * fraction) - 1)]


def finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PerformanceError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise PerformanceError(f"{field} must be finite")
    return number


def load_metrics(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PerformanceError(f"could not read performance JSON: {error}") from error
    if not isinstance(payload, dict):
        raise PerformanceError("performance JSON must contain an object")
    return payload


def validate(payload: dict[str, object], minimum_samples: int, maximum_p95_ms: float | None) -> dict[str, object]:
    failures: list[str] = []
    if payload.get("schema_version") != 1:
        failures.append("unsupported performance schema")
    if payload.get("platform") != "macos":
        failures.append("performance result is not for macOS")
    if payload.get("frame_time_unit") != "microseconds":
        failures.append("frame timings are not expressed in microseconds")
    if payload.get("fixture_entities") != 3:
        failures.append("performance fixture is incomplete")
    if payload.get("renderer") != "opengl-forward":
        failures.append("performance renderer profile does not match the baseline contract")

    raw_samples = payload.get("samples_us")
    values: list[float] = []
    if not isinstance(raw_samples, list):
        failures.append("samples_us must be an array")
    elif len(raw_samples) > MAX_SAMPLES:
        failures.append("performance result contains too many samples")
    else:
        for index, value in enumerate(raw_samples):
            try:
                number = finite_number(value, f"samples_us[{index}]")
            except PerformanceError as error:
                failures.append(str(error))
                break
            if number <= 0:
                failures.append("frame timings must be positive")
                break
            values.append(number)

    sorted_values = sorted(values)
    if len(values) < minimum_samples:
        failures.append(f"sample count {len(values)} is below required minimum {minimum_samples}")
    if payload.get("sample_count") != len(values):
        failures.append("reported sample count does not match samples_us")

    duration_ms = payload.get("duration_ms")
    try:
        duration = finite_number(duration_ms, "duration_ms")
        if duration < 1000 or duration > 300000:
            failures.append("measurement duration is outside the supported range")
    except PerformanceError as error:
        failures.append(str(error))
        duration = 0.0

    computed: dict[str, float] = {}
    if sorted_values:
        for field, calculate in REPORTED_FIELDS.items():
            expected = calculate(sorted_values)
            computed[field] = expected
            try:
                reported = finite_number(payload.get(field), field)
                tolerance = max(0.001, expected * 0.001)
                if abs(reported - expected) > tolerance:
                    failures.append(f"{field} does not match raw samples")
            except PerformanceError as error:
                failures.append(str(error))
        if maximum_p95_ms is not None and computed["p95_frame_ms"] > maximum_p95_ms:
            failures.append(
                f"p95 frame time {computed['p95_frame_ms']:.3f} ms exceeds {maximum_p95_ms:.3f} ms"
            )

    for field, threshold in (("over_16_67_ms", 16667), ("over_33_33_ms", 33333)):
        expected_count = sum(value > threshold for value in values)
        if payload.get(field) != expected_count:
            failures.append(f"{field} does not match raw samples")

    rates = payload.get("rates_hz")
    if not isinstance(rates, dict):
        failures.append("rates_hz must be an object")
    else:
        for name in ("render", "present", "new_frame", "dropped", "simulation"):
            try:
                if finite_number(rates.get(name), f"rates_hz.{name}") < 0:
                    failures.append(f"rates_hz.{name} must not be negative")
            except PerformanceError as error:
                failures.append(str(error))

    return {
        "passed": not failures,
        "schema_version": 1,
        "sample_count": len(values),
        "duration_ms": duration,
        **computed,
        "failures": failures,
    }


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise PerformanceError("refusing to replace a symlinked report")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def write_junit(path: Path, result: dict[str, object]) -> None:
    suite = ET.Element(
        "testsuite",
        name="overte.macos.performance",
        tests="1",
        failures="0" if result["passed"] else "1",
    )
    properties = ET.SubElement(suite, "properties")
    for name in ("sample_count", "duration_ms", "mean_frame_ms", "p95_frame_ms", "p99_frame_ms"):
        if name in result:
            ET.SubElement(properties, "property", name=name, value=str(result[name]))
    case = ET.SubElement(suite, "testcase", classname="overte.macos", name="frame-timing")
    if not result["passed"]:
        failure = ET.SubElement(case, "failure", message="macOS performance validation failed")
        failure.text = "\n".join(str(item) for item in result["failures"])
    atomic_write(path, ET.tostring(suite, encoding="utf-8", xml_declaration=True) + b"\n")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("metrics", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--minimum-samples", type=int, default=30)
    parser.add_argument("--maximum-p95-ms", type=float)
    arguments = parser.parse_args()
    if arguments.minimum_samples <= 0 or arguments.minimum_samples > MAX_SAMPLES:
        parser.error("--minimum-samples is outside the supported range")
    if arguments.maximum_p95_ms is not None and (
        not math.isfinite(arguments.maximum_p95_ms) or arguments.maximum_p95_ms <= 0
    ):
        parser.error("--maximum-p95-ms must be a positive finite value")
    return arguments


def main() -> int:
    arguments = parse_arguments()
    try:
        payload = load_metrics(arguments.metrics)
        result = validate(payload, arguments.minimum_samples, arguments.maximum_p95_ms)
        serialized = (json.dumps(result, sort_keys=True) + "\n").encode("utf-8")
        atomic_write(arguments.result, serialized)
        write_junit(arguments.junit, result)
    except PerformanceError as error:
        result = {"passed": False, "schema_version": 1, "failures": [str(error)]}
        try:
            atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
            write_junit(arguments.junit, result)
        except (OSError, PerformanceError) as write_error:
            print(f"could not publish validation reports: {write_error}", file=sys.stderr)
            return 2
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
