#!/usr/bin/env python3
"""Validate an Overte device adapter against the universal protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from adapter_client import load_command
from contracts import validate_capabilities


def call(command: list[str], *arguments: str) -> object:
    result = subprocess.run([*command, *arguments], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"adapter {arguments[0]} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"adapter {arguments[0]} returned invalid JSON") from error


def validate_target(target: object, selectors: set[str]) -> dict:
    if not isinstance(target, dict):
        raise ValueError("discover entries must be objects")
    required = {
        "selector": str,
        "displayName": str,
        "platform": str,
        "physical": bool,
        "capabilities": list,
    }
    for field, expected in required.items():
        if not isinstance(target.get(field), expected):
            raise ValueError(f"target field {field} has the wrong type")
    if not target["selector"] or target["selector"] in selectors:
        raise ValueError("target selectors must be unique non-empty strings")
    selectors.add(target["selector"])
    capabilities = target["capabilities"]
    if (not all(isinstance(item, str) and item for item in capabilities)
            or len(capabilities) != len(set(capabilities))):
        raise ValueError("target capabilities must be unique non-empty strings")
    if capabilities != sorted(capabilities):
        raise ValueError("target capabilities must use deterministic sorted order")
    validate_capabilities(capabilities)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-manifest", required=True, type=Path)
    parser.add_argument("--target", help="validate only this private selector")
    parser.add_argument("--check-cleanup", action="store_true",
                        help="call cleanup twice to verify its idempotent success contract")
    args = parser.parse_args()
    manifest = json.loads(args.adapter_manifest.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("id"), str):
        raise ValueError("invalid adapter manifest")
    command = load_command(args.adapter_manifest.resolve())
    discovered = call(command, "discover")
    if not isinstance(discovered, list):
        raise ValueError("discover must return a JSON list")
    selectors: set[str] = set()
    targets = [validate_target(item, selectors) for item in discovered]
    if args.target:
        targets = [target for target in targets if target["selector"] == args.target]
        if not targets:
            raise ValueError("requested target was not discovered")
    for target in targets:
        selector = target["selector"]
        description = call(command, "describe", "--target", selector)
        if not isinstance(description, dict):
            raise ValueError("describe must return a JSON object")
        serialized = json.dumps(description, sort_keys=True)
        if selector in serialized or "selector" in description:
            raise ValueError("describe must not expose the private target selector")
        if args.check_cleanup:
            for _ in range(2):
                cleaned = call(command, "cleanup", "--target", selector)
                if not isinstance(cleaned, dict):
                    raise ValueError("cleanup must return a JSON object")
    print(f"PASS: adapter {manifest['id']} satisfies the protocol for {len(targets)} target(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
