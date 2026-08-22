#!/usr/bin/env python3
"""Validate complete iPhone and iPad acceptance-result records."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PurePosixPath


OUTCOMES = {"pass", "fail", "blocked"}
FORM_FACTORS = {"iphone", "ipad"}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def validate_result(matrix: dict, result: dict, source: Path) -> str:
    if result.get("schemaVersion") != 1:
        raise ValueError(f"unsupported result schema in {source}")
    form_factor = result.get("formFactor")
    if form_factor not in FORM_FACTORS:
        raise ValueError(f"invalid form factor in {source}: {form_factor}")

    device = result.get("device", {})
    if set(device) != {"osVersion"}:
        raise ValueError(f"device record must contain only the OS version in {source}")
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", str(device.get("osVersion", ""))) is None:
        raise ValueError(f"device OS version is invalid in {source}")

    build = result.get("build", {})
    if re.fullmatch(r"[0-9a-f]{40}", str(build.get("sourceRevision", ""))) is None:
        raise ValueError(f"source revision is invalid in {source}")
    if re.fullmatch(r"[0-9a-f]{64}", str(build.get("bundleSha256", ""))) is None:
        raise ValueError(f"bundle digest is invalid in {source}")
    for field in ("xcode", "sdk"):
        if not isinstance(build.get(field), str) or not build[field].strip():
            raise ValueError(f"build {field} is missing in {source}")

    required_ids = [case["id"] for case in matrix["cases"]]
    records = result.get("results")
    if not isinstance(records, list):
        raise ValueError(f"results must be an array in {source}")
    record_ids = [record.get("id") for record in records if isinstance(record, dict)]
    if record_ids != required_ids:
        raise ValueError(f"result IDs or order differ from the acceptance matrix in {source}")

    for record in records:
        outcome = record.get("outcome")
        evidence = record.get("evidence")
        notes = record.get("notes")
        if outcome not in OUTCOMES:
            raise ValueError(f"invalid outcome for {record.get('id')} in {source}")
        if not isinstance(evidence, list) or len(evidence) != len(set(evidence)):
            raise ValueError(f"evidence must be a unique array for {record.get('id')} in {source}")
        for item in evidence:
            evidence_path = PurePosixPath(item)
            if not item or evidence_path.is_absolute() or ".." in evidence_path.parts:
                raise ValueError(f"unsafe evidence path for {record.get('id')} in {source}")
        if outcome in {"pass", "fail"} and not evidence:
            raise ValueError(f"{outcome} requires evidence for {record.get('id')} in {source}")
        if not isinstance(notes, str) or (outcome == "blocked" and not notes.strip()):
            raise ValueError(f"blocked results require notes for {record.get('id')} in {source}")
    return form_factor


def validate_files(matrix_path: Path, result_paths: list[Path]) -> None:
    matrix = load_json(matrix_path)
    if matrix.get("schemaVersion") != 1:
        raise ValueError("unsupported acceptance-matrix schema")
    required_form_factors = set(matrix.get("requiredFormFactors", []))
    if required_form_factors != FORM_FACTORS:
        raise ValueError("acceptance matrix must require iPhone and iPad")
    case_ids = [case.get("id") for case in matrix.get("cases", [])]
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("acceptance matrix case IDs must be present and unique")

    observed: list[str] = []
    for result_path in result_paths:
        observed.append(validate_result(matrix, load_json(result_path), result_path))
    if set(observed) != required_form_factors or len(observed) != len(required_form_factors):
        raise ValueError("provide exactly one complete result for iPhone and one for iPad")


def main() -> int:
    if len(sys.argv) < 4:
        print(f"usage: {sys.argv[0]} MATRIX IPHONE_RESULT IPAD_RESULT", file=sys.stderr)
        return 2
    try:
        validate_files(Path(sys.argv[1]), [Path(item) for item in sys.argv[2:]])
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("Verified complete iPhone and iPad acceptance results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
