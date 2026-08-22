#!/usr/bin/env python3
"""Generate a deterministic CycloneDX inventory from the audited iOS Conan graph."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REFERENCE_PATTERN = re.compile(r"([^/]+)/([^@#%:]+)")


def normalize_licenses(value) -> list[dict]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [item for item in value if isinstance(item, str)]
    else:
        values = []
    return [{"license": {"name": item}} for item in sorted(set(values)) if item.strip()]


def generate_sbom(graph: dict, inventory: dict) -> dict:
    policies = inventory["dependencies"]
    components: list[dict] = []
    build_tools: list[str] = []
    observed_target_names: set[str] = set()
    nodes = graph.get("graph", {}).get("nodes", {})
    if not isinstance(nodes, dict):
        raise ValueError("Conan graph nodes must be an object")
    for node in nodes.values():
        reference = node.get("ref") if isinstance(node, dict) else None
        if not reference:
            continue
        match = REFERENCE_PATTERN.match(reference)
        if match is None:
            raise ValueError(f"invalid Conan reference: {reference}")
        name, version = match.groups()
        if name == "overte-ios-dependencies":
            continue
        if node.get("context") == "build":
            build_tools.append(f"{name}/{version}")
            continue
        observed_target_names.add(name)
        policy = policies.get(name, {"class": "transitive", "ship": True})
        component = {
            "type": "library",
            "name": name,
            "version": version,
            "bom-ref": f"pkg:conan/{name}@{version}",
            "scope": "required" if policy.get("ship", True) else "excluded",
            "properties": [
                {"name": "overte:ios:classification", "value": policy["class"]},
                {"name": "overte:ios:privacy-review", "value": "required"},
                {
                    "name": "overte:ios:license-review",
                    "value": "recorded" if normalize_licenses(node.get("license")) else "required",
                },
            ],
        }
        licenses = normalize_licenses(node.get("license"))
        if licenses:
            component["licenses"] = licenses
        components.append(component)

    expected_direct = {
        name
        for name, policy in policies.items()
        if policy["ship"] and policy["class"] not in {"disabled", "deferred", "host-tool"}
    }
    unresolved = sorted(expected_direct - observed_target_names)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "Overte iOS",
                "version": "bootstrap",
            },
            "properties": [
                {"name": "overte:ios:target", "value": inventory["target"]},
                {"name": "overte:ios:build-tools", "value": ",".join(sorted(set(build_tools)))},
                {"name": "overte:ios:unresolved-direct", "value": ",".join(unresolved)},
            ],
        },
        "components": sorted(components, key=lambda component: component["bom-ref"]),
    }


def main() -> int:
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} CONAN_GRAPH INVENTORY OUTPUT", file=sys.stderr)
        return 2
    try:
        with Path(sys.argv[1]).open(encoding="utf-8") as stream:
            graph = json.load(stream)
        with Path(sys.argv[2]).open(encoding="utf-8") as stream:
            inventory = json.load(stream)
        payload = generate_sbom(graph, inventory)
        Path(sys.argv[3]).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Generated deterministic iOS SBOM: {sys.argv[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
