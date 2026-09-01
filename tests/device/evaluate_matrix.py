#!/usr/bin/env python3
"""Aggregate private device-run outputs into a selector-free acceptance matrix."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

GATE = re.compile(r"^[a-z][a-z0-9.-]*:[a-z][a-z0-9.-]*$")
RUN_FIELDS = {
    "adapter", "capabilities", "durationSeconds", "finishedEpochMs", "modules",
    "physical", "platform", "requireComplete", "schemaVersion", "startedEpochMs",
    "status", "suite",
}
SUMMARY_FIELDS = {"adapter", "results", "schemaVersion", "status", "suite"}
RESULT_FIELDS = {"description", "durationSeconds", "id", "returncode", "status"}


def fail(message: str) -> "NoReturn":
    raise ValueError(message)


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.name} must contain an object")
    return value


def validate_run(directory: Path, ordinal: int) -> dict:
    manifest = load_object(directory / "run-manifest.json")
    summary = load_object(directory / "summary.json")
    if manifest.get("schemaVersion") != 1 or set(manifest) != RUN_FIELDS:
        fail("unsupported run manifest contract")
    if summary.get("schemaVersion") != 1 or set(summary) != SUMMARY_FIELDS:
        fail("unsupported run summary contract")
    for field in ("adapter", "platform", "suite"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            fail(f"run manifest {field} must be non-empty")
    if (manifest["adapter"] != summary.get("adapter")
            or manifest["suite"] != summary.get("suite")
            or manifest.get("status") != summary.get("status")):
        fail("run manifest and summary identity disagree")
    if (manifest["status"] not in {"passed", "failed"}
            or not isinstance(manifest.get("physical"), bool)
            or not isinstance(manifest.get("requireComplete"), bool)
            or not isinstance(manifest.get("modules"), list)
            or not isinstance(manifest.get("capabilities"), list)):
        fail("run manifest contains invalid status or coverage fields")
    if (manifest["modules"] != list(dict.fromkeys(manifest["modules"]))
            or not all(isinstance(item, str) and item for item in manifest["modules"])
            or manifest["capabilities"] != sorted(set(manifest["capabilities"]))
            or not all(isinstance(item, str) and item for item in manifest["capabilities"])):
        fail("run manifest coverage lists are invalid")
    if (not isinstance(manifest.get("startedEpochMs"), int)
            or not isinstance(manifest.get("finishedEpochMs"), int)
            or manifest["startedEpochMs"] <= 0
            or manifest["finishedEpochMs"] < manifest["startedEpochMs"]
            or not isinstance(manifest.get("durationSeconds"), (int, float))
            or isinstance(manifest["durationSeconds"], bool)
            or manifest["durationSeconds"] < 0):
        fail("run manifest timing is invalid")
    results = summary.get("results")
    if not isinstance(results, list):
        fail("run summary results must be a list")
    counts = {status: 0 for status in ("passed", "failed", "error", "skipped")}
    for result in results:
        if not isinstance(result, dict) or set(result) != RESULT_FIELDS:
            fail("run summary contains an invalid module result")
        status = result.get("status")
        if status not in counts:
            fail("run summary contains an unknown module status")
        counts[status] += 1
    observed_status = "failed" if counts["failed"] or counts["error"] else "passed"
    if observed_status != manifest["status"]:
        fail("run status does not match its module results")
    return {
        "runId": f"run-{ordinal:03d}",
        "adapter": manifest["adapter"],
        "platform": manifest["platform"],
        "physical": manifest["physical"],
        "suite": manifest["suite"],
        "status": manifest["status"],
        "complete": (manifest["requireComplete"] and counts["skipped"] == 0
                     and counts["error"] == 0),
        "durationSeconds": manifest["durationSeconds"],
        "counts": counts,
    }


def junit(runs: list[dict], missing: list[str], path: Path) -> None:
    failures = sum(run["counts"]["failed"] > 0 for run in runs)
    errors = sum(run["counts"]["error"] > 0 for run in runs) + len(missing)
    root = ET.Element("testsuite", name="device-acceptance-matrix",
                      tests=str(len(runs) + len(missing)), failures=str(failures),
                      errors=str(errors), skipped="0",
                      time=f"{sum(run['durationSeconds'] for run in runs):.3f}")
    for run in runs:
        case = ET.SubElement(root, "testcase", classname="overte.device.matrix",
                             name=f"{run['runId']}:{run['platform']}:{run['suite']}",
                             time=f"{run['durationSeconds']:.3f}")
        if run["counts"]["error"]:
            ET.SubElement(case, "error", message="device infrastructure failure")
        elif run["counts"]["failed"]:
            ET.SubElement(case, "failure", message="E2E product assertion failure")
    for gate in missing:
        case = ET.SubElement(root, "testcase", classname="overte.device.matrix",
                             name=f"required:{gate}", time="0.000")
        ET.SubElement(case, "error", message="required complete physical run is missing")
    temporary = path.with_suffix(path.suffix + ".tmp")
    ET.ElementTree(root).write(temporary, encoding="utf-8", xml_declaration=True)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", action="append", required=True, type=Path,
                        help="device run output directory; repeat for every matrix cell")
    parser.add_argument("--require", action="append", default=[], dest="required",
                        help="required complete physical platform:suite gate")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    required = sorted(set(args.required))
    if any(not GATE.fullmatch(gate) for gate in required):
        fail("required gates must use platform:suite identifier syntax")
    output = args.output_dir.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        fail("matrix output directory must be absent or empty")
    output.mkdir(parents=True, mode=0o700)
    runs = [validate_run(path.resolve(), index)
            for index, path in enumerate(args.result, start=1)]
    satisfied = {
        f"{run['platform']}:{run['suite']}" for run in runs
        if run["physical"] and run["complete"]
    }
    missing = sorted(set(required) - satisfied)
    has_product_failure = any(run["counts"]["failed"] for run in runs)
    has_infrastructure_error = bool(missing) or any(run["counts"]["error"] for run in runs)
    status = ("error" if has_infrastructure_error else
              "failed" if has_product_failure else "passed")
    payload = {"schemaVersion": 1, "status": status, "required": required,
               "missing": missing, "runs": runs}
    (output / "matrix-summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    junit(runs, missing, output / "junit.xml")
    print(f"Matrix: {status}; {len(runs)} run(s), {len(missing)} missing gate(s)")
    return 2 if has_infrastructure_error else 1 if has_product_failure else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
