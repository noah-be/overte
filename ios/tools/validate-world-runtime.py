#!/usr/bin/env python3
"""Bind an iOS navigation request, runtime gates and screenshot to one world."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys


WORLD_PREFIX = "OVERTE_IOS_WORLD_GATE"
ENTITY_PREFIX = "OVERTE_IOS_ENTITY_GATE"
UUID = re.compile(
    r"^\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\}?$"
)
WORLD_FIELD = re.compile(r"\b(kind|destination|scene|success)=\s*([^\s]+)")
ENTITY_FIELD = re.compile(r"\b(domain|entity)=\s*([^\s]+)")
TRACE_FIELD = re.compile(
    r"\b(expected|renderables|scene|drawn|output|target|format|clip_finite)=\s*([^\s]+)"
)
FLOAT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def load_entity_validator():
    path = Path(__file__).with_name("validate-entity-gate-log.py")
    specification = importlib.util.spec_from_file_location("ios_entity_gate_validator", path)
    if specification is None or specification.loader is None:
        raise RuntimeError("entity gate validator is unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def marker(line: str, prefix: str) -> tuple[str, dict[str, str]] | None:
    match = re.search(rf"{re.escape(prefix)}\s+([a-z_]+)", line)
    if match is None:
        return None
    fields = dict((WORLD_FIELD if prefix == WORLD_PREFIX else ENTITY_FIELD).findall(line))
    return match.group(1), fields


def require_navigation(lines: list[str], scenario: str, destination: str) -> int:
    found: list[tuple[int, dict[str, str]]] = []
    for index, line in enumerate(lines):
        parsed = marker(line, WORLD_PREFIX)
        if parsed and parsed[0] == "navigation_requested":
            found.append((index, parsed[1]))
    if len(found) != 1:
        raise ValueError("expected exactly one iOS navigation request marker")
    index, fields = found[0]
    if fields != {"kind": scenario, "destination": destination}:
        raise ValueError("iOS navigation request does not match the selected world")
    return index


def validate_serverless_gates(
    lines: list[str], navigation_index: int, destination: str
) -> dict[str, object]:
    def find_after(prefix: str, expected_name: str, cursor: int) -> tuple[int, dict[str, str]]:
        for index in range(cursor, len(lines)):
            parsed = marker(lines[index], prefix)
            if parsed and parsed[0] == expected_name:
                return index, parsed[1]
        raise ValueError(f"missing serverless runtime gate {expected_name}")

    import_index, import_fields = find_after(
        WORLD_PREFIX, "serverless_import_committed", navigation_index + 1
    )
    if import_fields.get("scene") != destination:
        raise ValueError("serverless import committed a different scene")

    # Viewpoint application and render-scene handoff are independent consumers
    # of the committed import.  A queued root-viewpoint callback can complete
    # either before or after the render thread inserts the first entity, so do
    # not impose a false total order between those two valid paths.
    viewpoint_index, viewpoint_fields = find_after(
        WORLD_PREFIX, "serverless_viewpoint_applied", import_index + 1
    )
    if viewpoint_fields != {"success": "1"}:
        raise ValueError("serverless root viewpoint was not applied")

    tree_index, tree_fields = find_after(
        ENTITY_PREFIX, "entity_tree_nonempty", import_index + 1
    )
    tree_entity = tree_fields.get("entity", "")
    if UUID.fullmatch(tree_entity) is None:
        raise ValueError("entity_tree_nonempty has an invalid entity UUID")

    handoff_index, handoff_fields = find_after(
        ENTITY_PREFIX, "render_handoff", tree_index + 1
    )
    handoff_entity = handoff_fields.get("entity", "")
    if UUID.fullmatch(handoff_entity) is None:
        raise ValueError("render_handoff has an invalid entity UUID")
    if handoff_entity.strip("{}").lower() != tree_entity.strip("{}").lower():
        raise ValueError("serverless render entity differs from the decoded entity")

    evidence = [
        {
            "gate": "serverless_import_committed",
            "line": import_index + 1,
            "fields": import_fields,
        },
        {
            "gate": "serverless_viewpoint_applied",
            "line": viewpoint_index + 1,
            "fields": viewpoint_fields,
        },
        {
            "gate": "entity_tree_nonempty",
            "line": tree_index + 1,
            "fields": tree_fields,
        },
        {
            "gate": "render_handoff",
            "line": handoff_index + 1,
            "fields": handoff_fields,
        },
    ]
    evidence.sort(key=lambda item: int(item["line"]))
    return {"accepted": True, "evidence": evidence}


def trace_marker(line: str) -> tuple[str, dict[str, str]] | None:
    match = re.search(r"\bOVERTE_IOS_ENTITY_TRACE\s+stage=([a-z_]+)", line)
    if match is None:
        return None
    return match.group(1), dict(TRACE_FIELD.findall(line))


def positive(fields: dict[str, str], *names: str) -> bool:
    try:
        return all(int(fields[name]) > 0 for name in names)
    except (KeyError, ValueError):
        return False


def vector(line: str, name: str) -> tuple[float, float, float] | None:
    match = re.search(rf"\b{re.escape(name)}=\s*({FLOAT})\s+({FLOAT})\s+({FLOAT})(?:\s|$)", line)
    if match is None:
        return None
    values = tuple(float(value) for value in match.groups())
    return values if all(math.isfinite(value) for value in values) else None


def validate_serverless_trace(lines: list[str], navigation_index: int) -> dict[str, object]:
    """Accept repeated committed render traces when Apple drops early one-shot gates."""
    cpu = gpu = camera = None
    for index in range(navigation_index + 1, len(lines)):
        parsed = trace_marker(lines[index])
        if parsed is None:
            continue
        stage, fields = parsed
        if (
            cpu is None
            and stage == "cpu_cull"
            and positive(fields, "expected", "scene", "drawn", "output")
        ):
            cpu = (index, fields)
        elif (
            gpu is None
            and stage == "gpu_draw"
            and fields.get("target") == "1"
            and fields.get("format") == "present"
            and fields.get("clip_finite") == "1"
        ):
            gpu = (index, fields)
        elif (
            camera is None
            and stage == "camera"
            and positive(fields, "expected", "renderables", "scene", "drawn")
        ):
            camera_position = vector(lines[index], "camera")
            avatar_position = vector(lines[index], "avatar")
            direction = vector(lines[index], "direction")
            if camera_position is None or avatar_position is None or direction is None:
                continue
            # The bundled tutorial is authored near (2000, 2000, 2000).  Both
            # positions must therefore be well clear of the former physics
            # reset at the origin, close to one another, and have a real view
            # direction.  This binds the fallback to the fixed viewpoint path.
            separation = math.dist(camera_position, avatar_position)
            if (
                max(abs(value) for value in camera_position) <= 100.0
                or max(abs(value) for value in avatar_position) <= 100.0
                or separation >= 100.0
                or math.sqrt(sum(value * value for value in direction)) < 0.5
            ):
                continue
            camera = (index, fields)

    if cpu is None:
        raise ValueError("missing committed serverless CPU render trace")
    if gpu is None:
        raise ValueError("missing finite serverless world GPU draw trace")
    if camera is None:
        raise ValueError("missing stable serverless viewpoint trace")

    evidence = [
        {"gate": "serverless_trace_committed", "line": cpu[0] + 1, "fields": cpu[1]},
        {"gate": "serverless_trace_world_draw", "line": gpu[0] + 1, "fields": gpu[1]},
        {"gate": "serverless_trace_viewpoint", "line": camera[0] + 1, "fields": camera[1]},
    ]
    evidence.sort(key=lambda item: int(item["line"]))
    return {"accepted": True, "evidenceMode": "committed-render-trace", "evidence": evidence}


def validate_serverless(lines: list[str], navigation_index: int, destination: str) -> dict[str, object]:
    # Explicit contradictory gates are never masked by fallback diagnostics.
    for line in lines[navigation_index + 1 :]:
        parsed = marker(line, WORLD_PREFIX)
        if parsed and parsed[0] == "serverless_import_committed":
            if parsed[1].get("scene") != destination:
                raise ValueError("serverless import committed a different scene")
        if parsed and parsed[0] == "serverless_viewpoint_applied":
            if parsed[1] != {"success": "1"}:
                raise ValueError("serverless root viewpoint was not applied")

    try:
        return validate_serverless_gates(lines, navigation_index, destination)
    except ValueError as gate_error:
        try:
            return validate_serverless_trace(lines, navigation_index)
        except ValueError as trace_error:
            raise gate_error from trace_error


def validate_online(
    lines: list[str], navigation_index: int, expected_domain: str
) -> dict[str, object]:
    if UUID.fullmatch(expected_domain) is None:
        raise ValueError("expected online domain ID is not a UUID")
    entity_validator = load_entity_validator()
    report = entity_validator.validate(lines[navigation_index + 1 :])
    if not report.get("accepted"):
        errors = report.get("errors") or ["online entity gates were rejected"]
        raise ValueError(str(errors[0]))
    evidence = report["evidence"]
    actual_domain = evidence[0]["fields"]["domain"].strip("{}").lower()
    if actual_domain != expected_domain.strip("{}").lower():
        raise ValueError("connected domain does not match the resolved online world")
    return report


def validate(
    log: Path,
    scenario: str,
    destination: str,
    expected_domain: str | None,
    screenshot_path: Path,
    screenshot_report: Path,
) -> dict[str, object]:
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    navigation_index = require_navigation(lines, scenario, destination)
    if scenario == "serverless":
        runtime = validate_serverless(lines, navigation_index, destination)
        domain = None
    else:
        if expected_domain is None:
            raise ValueError("online validation requires an expected domain ID")
        runtime = validate_online(lines, navigation_index, expected_domain)
        domain = expected_domain.strip("{}").lower()

    screenshot = json.loads(screenshot_report.read_text(encoding="utf-8"))
    if screenshot.get("accepted") is not True:
        raise ValueError("world screenshot was not accepted")
    if screenshot.get("scenario") != scenario or screenshot.get("destination") != destination:
        raise ValueError("screenshot report belongs to a different world")
    screenshot_sha256 = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
    if screenshot.get("file") != screenshot_path.name or screenshot.get("sha256") != screenshot_sha256:
        raise ValueError("screenshot report does not match the retained screenshot")
    return {
        "schemaVersion": 1,
        "accepted": True,
        "scenario": scenario,
        "destination": destination,
        "resolvedDomainId": domain,
        "navigationLine": navigation_index + 1,
        "runtime": runtime,
        "screenshot": screenshot,
        "containsRawRuntimeLog": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--scenario", choices=("serverless", "online"), required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--expected-domain")
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--screenshot-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate(
            args.log,
            args.scenario,
            args.destination,
            args.expected_domain,
            args.screenshot,
            args.screenshot_report,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
