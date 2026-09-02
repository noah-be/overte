#!/usr/bin/env python3
"""Validate an Overte device adapter against the universal protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from adapter_client import load_command
from contracts import (contains_private_identity, validate_discovered_targets,
                       validate_operation_result)


def call(command: list[str], *arguments: str) -> object:
    result = subprocess.run([*command, *arguments], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"adapter {arguments[0]} failed"
        if "--target" in arguments:
            detail = detail.replace(arguments[arguments.index("--target") + 1], "<target>")
        raise ValueError(detail)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"adapter {arguments[0]} returned invalid JSON") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-manifest", required=True, type=Path)
    parser.add_argument("--target", help="validate only this private selector")
    parser.add_argument("--require-target", action="store_true",
                        help="fail when discovery returns no eligible target")
    parser.add_argument("--check-cleanup", action="store_true",
                        help="call cleanup twice to verify its idempotent success contract")
    args = parser.parse_args()
    manifest = json.loads(args.adapter_manifest.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("id"), str):
        raise ValueError("invalid adapter manifest")
    command = load_command(args.adapter_manifest.resolve())
    targets = validate_discovered_targets(call(command, "discover"))
    if args.target:
        targets = [target for target in targets if target["selector"] == args.target]
        if not targets:
            raise ValueError("requested target was not discovered")
    if args.require_target and not targets:
        raise ValueError("adapter returned no target")
    for target in targets:
        selector = target["selector"]
        description = call(command, "describe", "--target", selector)
        if not isinstance(description, dict):
            raise ValueError("describe must return a JSON object")
        private_values = [selector]
        if isinstance(target.get("reservationKey"), str):
            private_values.append(target["reservationKey"])
        if ("selector" in description
                or contains_private_identity(description, private_values)):
            raise ValueError("describe must not expose the private target selector")
        if args.check_cleanup:
            for _ in range(2):
                cleaned = call(command, "cleanup", "--target", selector)
                validate_operation_result("cleanup", cleaned)
    print(f"PASS: adapter {manifest['id']} satisfies the protocol for {len(targets)} target(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
