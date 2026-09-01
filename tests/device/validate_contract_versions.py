#!/usr/bin/env python3
"""Enforce the machine-readable compatibility and migration registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = {
    "acceptance-policy": 1, "adapter-manifest": 1, "artifact-manifest": 1,
    "capability-registry": 1, "fixture-environment": 1, "matrix-summary": 1,
    "probe-snapshot": 2, "run-manifest": 1, "run-summary": 1, "timeline": 1,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry", type=Path,
        default=Path(__file__).resolve().with_name("contract-versions.json"))
    args = parser.parse_args()
    value = json.loads(args.registry.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or value.get("schemaVersion") != 1
            or set(value) != {"schemaVersion", "contracts", "migrationRules"}
            or set(value.get("contracts", {})) != set(REQUIRED)):
        raise ValueError("contract version registry shape is invalid")
    for name, expected in REQUIRED.items():
        item = value["contracts"][name]
        if (not isinstance(item, dict) or set(item) != {"current", "reads"}
                or item.get("current") != expected
                or not isinstance(item.get("reads"), list)
                or item["reads"] != sorted(set(item["reads"]))
                or expected not in item["reads"]
                or not all(isinstance(version, int) and version > 0
                           for version in item["reads"])):
            raise ValueError(f"contract {name} compatibility declaration is invalid")
    rules = value["migrationRules"]
    if (not isinstance(rules, dict)
            or set(rules) != {"additiveChange", "breakingChange", "removal"}
            or not all(isinstance(text, str) and text for text in rules.values())):
        raise ValueError("contract migration rules are invalid")
    root = args.registry.resolve().parent
    observed = {
        "capability-registry": json.loads(
            (root / "capabilities.json").read_text(encoding="utf-8"))["schemaVersion"],
        "run-manifest": json.loads(
            (root / "schemas/run-manifest.schema.json").read_text(encoding="utf-8"))[
                "properties"]["schemaVersion"]["const"],
        "matrix-summary": json.loads(
            (root / "schemas/matrix-summary.schema.json").read_text(encoding="utf-8"))[
                "properties"]["schemaVersion"]["const"],
        "probe-snapshot": json.loads(
            (root / "schemas/probe-snapshot.schema.json").read_text(encoding="utf-8"))[
                "properties"]["schemaVersion"]["const"],
    }
    acceptance_policy = root / "acceptance-policy.json"
    if acceptance_policy.is_file():
        observed["acceptance-policy"] = json.loads(
            acceptance_policy.read_text(encoding="utf-8"))["contractVersion"]
    for name, version in observed.items():
        if value["contracts"][name]["current"] != version:
            raise ValueError(f"contract {name} registry and producer version disagree")
    print("PASS: contract versions and migration rules are coherent")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=__import__("sys").stderr)
        raise SystemExit(2)
