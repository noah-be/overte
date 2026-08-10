#!/usr/bin/env python3
"""Host tests for physical-device acceptance result validation."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]
MATRIX = IOS_ROOT / "tests/device-acceptance.json"


def load_validator():
    path = IOS_ROOT / "tools/validate-device-results.py"
    specification = importlib.util.spec_from_file_location("validate_device_results", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def make_result(case_ids: list[str], form_factor: str) -> dict:
    return {
        "schemaVersion": 1,
        "formFactor": form_factor,
        "device": {"model": f"Test {form_factor}", "osVersion": "26.0"},
        "build": {
            "sourceRevision": "a" * 40,
            "bundleSha256": "b" * 64,
            "xcode": "26.2",
            "sdk": "26.1",
        },
        "results": [
            {
                "id": case_id,
                "outcome": "pass",
                "evidence": [f"evidence/{form_factor}/{case_id}.txt"],
                "notes": "",
            }
            for case_id in case_ids
        ],
    }


def main() -> None:
    validator = load_validator()
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    case_ids = [case["id"] for case in matrix["cases"]]
    with tempfile.TemporaryDirectory(prefix="overte-ios-results-") as temporary:
        root = Path(temporary)
        paths = []
        for form_factor in ("iphone", "ipad"):
            path = root / f"{form_factor}.json"
            path.write_text(
                json.dumps(make_result(case_ids, form_factor)), encoding="utf-8"
            )
            paths.append(path)
        validator.validate_files(MATRIX, paths)

        invalid = make_result(case_ids, "iphone")
        invalid["results"][0]["evidence"] = ["../outside.log"]
        invalid_path = root / "invalid.json"
        invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
        try:
            validator.validate_result(matrix, invalid, invalid_path)
        except ValueError as error:
            assert "unsafe evidence path" in str(error)
        else:
            raise AssertionError("unsafe evidence path was accepted")

    print("PASS iOS device-result validator tests")


if __name__ == "__main__":
    main()
