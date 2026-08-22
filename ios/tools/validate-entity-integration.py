#!/usr/bin/env python3
"""Validate that the iOS entity integration inventory still matches Overte sources."""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "ios/entity-integration-inventory.json"
PACKET_HEADER = ROOT / "libraries/networking/src/udt/PacketHeaders.h"


def fail(message):
    print(f"entity-integration inventory: {message}", file=sys.stderr)
    return 1


def main():
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        return fail("unsupported schema_version")
    if not data.get("policy", {}).get("reuse_existing_protocol"):
        return fail("existing protocol reuse must remain mandatory")
    if data.get("policy", {}).get("protocol_reimplementation_allowed"):
        return fail("protocol reimplementation must remain forbidden")

    targets = data.get("targets", {})
    stages = data.get("stages", [])
    if not targets or not stages:
        return fail("targets and stages must be non-empty")

    errors = []
    packet_text = PACKET_HEADER.read_text(encoding="utf-8")
    seen_ids = set()
    for name, target in targets.items():
        cmake = ROOT / target["cmake"]
        if not cmake.is_file():
            errors.append(f"target {name}: missing {target['cmake']}")
            continue
        cmake_text = cmake.read_text(encoding="utf-8")
        if not re.search(rf"set\s*\(TARGET_NAME\s+{re.escape(name)}\s*\)", cmake_text):
            errors.append(f"target {name}: TARGET_NAME declaration not found")

    for stage in stages:
        stage_id = stage.get("id")
        if not stage_id or stage_id in seen_ids:
            errors.append(f"invalid or duplicate stage id: {stage_id!r}")
        seen_ids.add(stage_id)
        if stage.get("target") not in targets:
            errors.append(f"stage {stage_id}: unknown target {stage.get('target')!r}")
        if not stage.get("gate"):
            errors.append(f"stage {stage_id}: missing gate")
        for source in stage.get("sources", []):
            path = ROOT / source["path"]
            if not path.is_file():
                errors.append(f"stage {stage_id}: missing {source['path']}")
                continue
            source_text = path.read_text(encoding="utf-8", errors="replace")
            for anchor in source.get("anchors", []):
                if anchor not in source_text:
                    errors.append(f"stage {stage_id}: anchor {anchor!r} absent from {source['path']}")
        for packet in stage.get("packets", []):
            if not re.search(rf"\b{re.escape(packet)}\b", packet_text):
                errors.append(f"stage {stage_id}: unknown packet {packet}")

    required_gates = {"domain-list-received", "entity-tree-nonempty", "real-entity-render-item-visible-on-ipad"}
    missing = required_gates.difference(data.get("acceptance_gates", []))
    if missing:
        errors.append("missing acceptance gates: " + ", ".join(sorted(missing)))
    if errors:
        return fail("\n  - " + "\n  - ".join(errors))
    print(f"entity-integration inventory valid: {len(targets)} targets, {len(stages)} stages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
