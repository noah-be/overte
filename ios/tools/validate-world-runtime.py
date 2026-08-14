#!/usr/bin/env python3
"""Bind an iOS navigation request, runtime gates and screenshot to one world."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


WORLD_PREFIX = "OVERTE_IOS_WORLD_GATE"
ENTITY_PREFIX = "OVERTE_IOS_ENTITY_GATE"
UUID = re.compile(
    r"^\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\}?$"
)
WORLD_FIELD = re.compile(r"\b(kind|destination|scene)=\s*([^\s]+)")
ENTITY_FIELD = re.compile(r"\b(domain|entity)=\s*([^\s]+)")


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


def validate_serverless(lines: list[str], navigation_index: int, destination: str) -> dict[str, object]:
    expected = (
        (WORLD_PREFIX, "serverless_import_committed"),
        (ENTITY_PREFIX, "entity_tree_nonempty"),
        (ENTITY_PREFIX, "render_handoff"),
    )
    evidence: list[dict[str, object]] = []
    cursor = navigation_index + 1
    for prefix, expected_name in expected:
        found = None
        for index in range(cursor, len(lines)):
            parsed = marker(lines[index], prefix)
            if parsed and parsed[0] == expected_name:
                found = (index, parsed[1])
                break
        if found is None:
            raise ValueError(f"missing serverless runtime gate {expected_name}")
        index, fields = found
        if expected_name == "serverless_import_committed" and fields.get("scene") != destination:
            raise ValueError("serverless import committed a different scene")
        if expected_name in ("entity_tree_nonempty", "render_handoff"):
            entity = fields.get("entity", "")
            if UUID.fullmatch(entity) is None:
                raise ValueError(f"{expected_name} has an invalid entity UUID")
            if expected_name == "render_handoff":
                previous = str(evidence[-1]["fields"]["entity"]).strip("{}").lower()
                if entity.strip("{}").lower() != previous:
                    raise ValueError("serverless render entity differs from the decoded entity")
        evidence.append({"gate": expected_name, "line": index + 1, "fields": fields})
        cursor = index + 1
    return {"accepted": True, "evidence": evidence}


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
