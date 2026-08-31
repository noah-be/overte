#!/usr/bin/env python3
"""Validate an Overte device adapter against the universal protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from adapter_client import load_command
from contracts import contains_private_identity, validate_discovered_targets
from acceptance_policy import STATES, load_policy, state_for
from run import load_modules

ROOT = Path(__file__).resolve().parent


def portable_baseline() -> set[str]:
    payload = json.loads((ROOT / "platform-adapters.json").read_text(encoding="utf-8"))
    required = payload.get("requiredCapabilities")
    if (payload.get("schemaVersion") != 1 or payload.get("contractVersion") != 1
            or payload.get("cleanupAction") != "cleanup"
            or not isinstance(required, list) or not required
            or required != sorted(set(required))):
        raise ValueError("portable platform adapter baseline is invalid")
    return set(required)


def call(command: list[str], *arguments: str) -> object:
    result = subprocess.run([*command, *arguments], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"adapter {arguments[0]} failed"
        if "--target" in arguments:
            target_index = arguments.index("--target") + 1
            if target_index < len(arguments):
                detail = detail.replace(arguments[target_index], "<target>")
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
    parser.add_argument("--policy", type=Path,
                        help="also verify promoted suite capability coverage")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--minimum-state", choices=STATES, default="accepted")
    parser.add_argument("--portable-baseline", action="store_true",
                        help="require the common install, smoke, evidence and cleanup contract")
    parser.add_argument("--require-capability", action="append", default=[],
                        help="require one advertised capability on every selected target")
    args = parser.parse_args()
    manifest = json.loads(args.adapter_manifest.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("id"), str):
        raise ValueError("invalid adapter manifest")
    command = load_command(args.adapter_manifest.resolve())
    if bool(args.policy) != bool(args.catalog):
        raise ValueError("--policy and --catalog must be supplied together")
    policy = (load_policy(args.policy.resolve(), args.catalog.resolve())
              if args.policy else None)
    required_explicit = set(args.require_capability)
    registry = json.loads((ROOT / "capabilities.json").read_text(encoding="utf-8"))[
        "capabilities"]
    unknown = sorted(required_explicit - set(registry))
    if unknown:
        raise ValueError("unknown required capabilities: " + ", ".join(unknown))
    if args.portable_baseline:
        required_explicit.update(portable_baseline())
        args.check_cleanup = True
    targets = validate_discovered_targets(call(command, "discover"))
    if args.target:
        targets = [target for target in targets if target["selector"] == args.target]
        if not targets:
            raise ValueError("requested target was not discovered")
    if args.require_target and not targets:
        raise ValueError("adapter discovery returned no target")
    for target in targets:
        selector = target["selector"]
        description = call(command, "describe", "--target", selector)
        if not isinstance(description, dict):
            raise ValueError("describe must return a JSON object")
        private_values = {selector, target.get("reservationKey", selector)}
        if ("selector" in description
                or contains_private_identity(description, private_values)):
            raise ValueError("describe must not expose the private target selector")
        missing_explicit = sorted(required_explicit - set(target["capabilities"]))
        if missing_explicit:
            raise ValueError(
                "adapter lacks portable baseline capabilities: "
                + ", ".join(missing_explicit))
        if args.check_cleanup:
            for _ in range(2):
                cleaned = call(command, "cleanup", "--target", selector)
                if not isinstance(cleaned, dict) or cleaned.get("cleaned") is not True:
                    raise ValueError("cleanup must return cleaned: true")
        if policy is not None:
            threshold = STATES.index(args.minimum_state)
            required_capabilities = set()
            for suite in sorted({suite for module in json.loads(
                    args.catalog.read_text(encoding="utf-8"))["modules"]
                    for suite in module["suites"]}):
                if STATES.index(state_for(policy, target["platform"], suite)) >= threshold:
                    for module in load_modules(args.catalog.resolve(), suite):
                        required_capabilities.update(module["requires"])
            missing = sorted(required_capabilities - set(target["capabilities"]))
            if missing:
                raise ValueError(
                    "adapter lacks promoted suite capabilities: " + ", ".join(missing))
    print(f"PASS: adapter {manifest['id']} satisfies the protocol for {len(targets)} target(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
