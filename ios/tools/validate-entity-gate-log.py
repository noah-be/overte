#!/usr/bin/env python3
"""Validate an iOS device log against the native entity integration gates."""

import argparse
import json
import pathlib
import re
import sys

PREFIX = "OVERTE_IOS_ENTITY_GATE"
GATES = (
    "domain_list_connected",
    "entity_server_active",
    "entity_query_sent",
    "entity_data_received",
    "entity_tree_nonempty",
    "render_handoff",
)
UUID = re.compile(r"^\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\}?$")
FIELD = re.compile(r"\b(domain|session|node|entity|bytes)=\s*([^\s]+)")


def parse_fields(line):
    return dict(FIELD.findall(line))


def validate(lines):
    evidence = []
    errors = []
    expected_index = 0
    entity_server_id = None

    for line_number, line in enumerate(lines, 1):
        marker_match = re.search(rf"{PREFIX}\s+([a-z_]+)", line)
        if not marker_match:
            continue
        marker = marker_match.group(1)
        if marker not in GATES:
            errors.append(f"line {line_number}: unknown entity gate marker {marker!r}")
            continue
        marker_index = GATES.index(marker)
        if marker_index < expected_index:
            # Repeated telemetry, such as periodic EntityQuery, is harmless once
            # that gate has already passed.
            continue
        if marker_index != expected_index:
            errors.append(
                f"line {line_number}: expected {GATES[expected_index]!r} before {marker!r}"
            )
            break

        fields = parse_fields(line)
        required = {
            "domain_list_connected": ("domain", "session"),
            "entity_server_active": ("node",),
            "entity_query_sent": ("node", "bytes"),
            "entity_data_received": ("node", "bytes"),
            "entity_tree_nonempty": ("entity",),
            "render_handoff": ("entity",),
        }[marker]
        missing = [name for name in required if name not in fields]
        if missing:
            errors.append(f"line {line_number}: {marker} missing field(s): {', '.join(missing)}")
            break
        for name in ("domain", "session", "node", "entity"):
            if name in fields and not UUID.fullmatch(fields[name]):
                errors.append(f"line {line_number}: {marker} has invalid {name} UUID")
        if "bytes" in fields and (not fields["bytes"].isdigit() or int(fields["bytes"]) <= 0):
            errors.append(f"line {line_number}: {marker} bytes must be a positive integer")

        if marker == "entity_server_active":
            entity_server_id = fields["node"].strip("{}").lower()
        elif marker in ("entity_query_sent", "entity_data_received"):
            if fields["node"].strip("{}").lower() != entity_server_id:
                errors.append(f"line {line_number}: {marker} node differs from active entity server")
        elif marker == "render_handoff":
            tree_entity = evidence[-1]["fields"]["entity"].strip("{}").lower()
            if fields["entity"].strip("{}").lower() != tree_entity:
                errors.append(f"line {line_number}: render entity differs from decoded tree entity")

        evidence.append({"gate": marker, "line": line_number, "fields": fields})
        expected_index += 1
        if errors:
            break

    if expected_index < len(GATES) and not errors:
        errors.append(f"missing gate {GATES[expected_index]!r}")

    return {
        "schema_version": 1,
        "accepted": not errors and expected_index == len(GATES),
        "expected_gates": list(GATES),
        "completed_gates": [item["gate"] for item in evidence],
        "evidence": evidence,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=pathlib.Path, help="exported iOS device log")
    parser.add_argument("--output", type=pathlib.Path, help="write JSON report to this path")
    args = parser.parse_args()
    report = validate(args.log.read_text(encoding="utf-8", errors="replace").splitlines())
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
