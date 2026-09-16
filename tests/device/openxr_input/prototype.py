#!/usr/bin/env python3
"""Inspect or compile the device-free OpenXR E2E input prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from protocol import ContractError, compile_envelope, profile_fingerprint


def _read(path: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read JSON input: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"JSON input must be an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    fingerprint = subparsers.add_parser("fingerprint")
    fingerprint.add_argument("--profile", required=True)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--profile", required=True)
    compile_parser.add_argument("--grant", required=True)
    compile_parser.add_argument("--commands", required=True)
    compile_parser.add_argument("--now-ms", required=True, type=int)
    compile_parser.add_argument("--allow-prototype", action="store_true")
    args = parser.parse_args()

    profile = _read(args.profile)
    if args.action == "fingerprint":
        print(profile_fingerprint(profile))
        return 0
    if not args.allow_prototype:
        raise ContractError("compile requires explicit --allow-prototype opt-in")
    output = compile_envelope(_read(args.commands), _read(args.grant),
                              profile, args.now_ms)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
