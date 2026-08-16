#!/usr/bin/env python3
"""Classify a CGL probe without exposing volatile host inventory."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys


class ProbeError(ValueError):
    pass


REQUIRED_FIELDS = {
    "schema_version",
    "pixel_format_count",
    "choose_error",
    "context_error",
    "context_created",
    "accelerated",
    "renderer_id",
    "virtual_screen_count",
}
OPTIONAL_FIELDS = {"gl_vendor", "gl_renderer", "gl_version", "glsl_version"}
DIAGNOSTIC_RENDERER_TOKENS = (
    "software",
    "paravirtual",
    "virtual",
    "swiftshader",
    "llvmpipe",
    "softpipe",
)


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_probe(path: Path) -> dict[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProbeError("CGL probe output is not valid JSON") from error
    if not isinstance(value, dict):
        raise ProbeError("CGL probe output must be an object")
    if set(value) - (REQUIRED_FIELDS | OPTIONAL_FIELDS) or not REQUIRED_FIELDS <= set(value):
        raise ProbeError("CGL probe output has an unexpected field set")
    return value


def classify(probe: dict[str, object], machine: str, translated: str) -> dict[str, object]:
    if probe.get("schema_version") != 1:
        raise ProbeError("unsupported CGL probe schema")
    for field in ("pixel_format_count", "choose_error", "context_error", "renderer_id",
                  "virtual_screen_count"):
        if isinstance(probe.get(field), bool) or not isinstance(probe.get(field), int):
            raise ProbeError(f"CGL probe field {field} must be an integer")
    for field in ("context_created", "accelerated"):
        if not isinstance(probe.get(field), bool):
            raise ProbeError(f"CGL probe field {field} must be boolean")
    for field in OPTIONAL_FIELDS:
        if field in probe and not isinstance(probe[field], str):
            raise ProbeError(f"CGL probe field {field} must be a string")
    if translated not in {"0", "1"}:
        raise ProbeError("translation state must be 0 or 1")

    renderer = str(probe.get("gl_renderer", ""))
    version = str(probe.get("gl_version", ""))
    match = re.match(r"^(\d+)\.(\d+)", version)
    opengl_41 = bool(match and tuple(map(int, match.groups())) >= (4, 1))
    hardware_renderer = bool(renderer) and not any(
        token in renderer.casefold() for token in DIAGNOSTIC_RENDERER_TOKENS
    )
    native_arm = machine == "arm64" and translated == "0"
    eligible = (
        native_arm
        and probe["pixel_format_count"] > 0
        and probe["choose_error"] == 0
        and probe["context_error"] == 0
        and probe["context_created"] is True
        and probe["accelerated"] is True
        and opengl_41
        and hardware_renderer
    )
    return {
        "schema_version": 1,
        "machine": machine,
        "translated": translated == "1",
        "context_created": probe["context_created"],
        "accelerated": probe["accelerated"],
        "gl_vendor": str(probe.get("gl_vendor", "")),
        "gl_renderer": renderer,
        "gl_version": version,
        "opengl_41": opengl_41,
        "hardware_eligible": eligible,
        "classification": "native-hardware" if eligible else "diagnostic-only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", type=Path)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--translated", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--require-hardware", action="store_true")
    arguments = parser.parse_args()
    try:
        result = classify(load_probe(arguments.probe), arguments.machine, arguments.translated)
    except ProbeError as error:
        print(f"Apple GPU probe validation failed: {error}", file=sys.stderr)
        return 1
    arguments.result.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.result.with_name(arguments.result.name + ".tmp")
    temporary.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, arguments.result)
    print(json.dumps(result, sort_keys=True), flush=True)
    if arguments.require_hardware and result["hardware_eligible"] is not True:
        print("runner does not provide native accelerated OpenGL 4.1", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
