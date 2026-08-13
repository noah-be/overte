#!/usr/bin/env python3
"""Summarize repeated macOS serverless launch/render/quit cycles."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET


REQUIRED_MARKERS = (
    "OVERTE_MACOS_ENTITY_GATE serverless_import_committed",
    "OVERTE_MACOS_ENTITY_GATE entity_tree_nonempty",
    "OVERTE_MACOS_ENTITY_GATE render_handoff",
    "OVERTE_MACOS_SMOKE passed",
)


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("refusing to replace a symlinked report")
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


def load_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root is not an object")
    return payload


def inspect_run(root: Path, index: int) -> dict[str, object]:
    name = f"run-{index:02d}"
    directory = root / name
    failures: list[str] = []
    elapsed = 0.0
    try:
        process = load_object(directory / "serverless-process.json")
        elapsed_value = process.get("elapsed_seconds")
        if isinstance(elapsed_value, bool) or not isinstance(elapsed_value, (int, float)):
            failures.append("invalid elapsed time")
        elif not math.isfinite(float(elapsed_value)) or float(elapsed_value) < 0:
            failures.append("invalid elapsed time")
        else:
            elapsed = float(elapsed_value)
        if process.get("exit_code") != 0:
            failures.append("application exit was not zero")
        if process.get("timed_out") is not False:
            failures.append("application timed out")
        if process.get("sent_sigterm") is not False or process.get("sent_sigkill") is not False:
            failures.append("application required a termination signal")
    except (OSError, json.JSONDecodeError, ValueError):
        failures.append("process evidence is missing or invalid")

    try:
        screenshot = load_object(directory / "serverless-screenshot.json")
        if screenshot.get("passed") is not True:
            failures.append("visual validation failed")
    except (OSError, json.JSONDecodeError, ValueError):
        failures.append("visual evidence is missing or invalid")

    try:
        log = (directory / "serverless.log").read_text(encoding="utf-8", errors="replace")
        for marker in REQUIRED_MARKERS:
            if marker not in log:
                failures.append(f"missing runtime marker: {marker.rsplit(' ', 1)[-1]}")
    except OSError:
        failures.append("runtime log is missing")

    return {
        "name": name,
        "passed": not failures,
        "elapsed_seconds": elapsed,
        "failures": failures,
    }


def write_junit(path: Path, runs: list[dict[str, object]]) -> None:
    failed = sum(not run["passed"] for run in runs)
    suite = ET.Element(
        "testsuite",
        name="overte.macos.stability",
        tests=str(len(runs)),
        failures=str(failed),
        time=f"{sum(float(run['elapsed_seconds']) for run in runs):.3f}",
    )
    for run in runs:
        case = ET.SubElement(
            suite,
            "testcase",
            classname="overte.macos.stability",
            name=str(run["name"]),
            time=f"{float(run['elapsed_seconds']):.3f}",
        )
        if not run["passed"]:
            failure = ET.SubElement(case, "failure", message="macOS stability cycle failed")
            failure.text = "\n".join(str(item) for item in run["failures"])
    atomic_write(path, ET.tostring(suite, encoding="utf-8", xml_declaration=True) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", type=Path)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.iterations < 1 or arguments.iterations > 20:
        parser.error("--iterations must be between 1 and 20")

    runs = [inspect_run(arguments.runs, index) for index in range(1, arguments.iterations + 1)]
    passed = sum(run["passed"] for run in runs)
    result = {
        "passed": passed == arguments.iterations,
        "schema_version": 1,
        "iterations": arguments.iterations,
        "passed_iterations": passed,
        "failed_iterations": arguments.iterations - passed,
        "total_elapsed_seconds": round(sum(float(run["elapsed_seconds"]) for run in runs), 3),
        "maximum_elapsed_seconds": round(max(float(run["elapsed_seconds"]) for run in runs), 3),
        "runs": runs,
    }
    try:
        atomic_write(arguments.result, (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"))
        write_junit(arguments.junit, runs)
    except OSError as error:
        print(f"could not publish stability reports: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
