#!/usr/bin/env python3
"""Validate and render the effective portable E2E acceptance policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acceptance_policy import gates, load_policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--minimum-state", choices=("implemented", "accepted", "required"),
                        default="required")
    args = parser.parse_args()
    policy = load_policy(args.policy.resolve(), args.catalog.resolve())
    effective = gates(policy, args.catalog.resolve(), args.minimum_state)
    print(json.dumps({"schemaVersion": 1, "minimumState": args.minimum_state,
                      "gates": effective}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=__import__("sys").stderr)
        raise SystemExit(2)
