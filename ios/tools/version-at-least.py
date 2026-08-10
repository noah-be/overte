#!/usr/bin/env python3
"""Compare the numeric tool versions used by the iOS build contract."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import sys


VERSION_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)*")


def parse_version(value: str) -> tuple[int, ...]:
    if VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid numeric version: {value}")
    return tuple(int(component) for component in value.split("."))


def version_at_least(actual: str, required: str) -> bool:
    actual_parts = parse_version(actual)
    required_parts = parse_version(required)
    width = max(len(actual_parts), len(required_parts))
    return actual_parts + (0,) * (width - len(actual_parts)) >= (
        required_parts + (0,) * (width - len(required_parts))
    )


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} ACTUAL REQUIRED", file=sys.stderr)
        return 2
    try:
        return 0 if version_at_least(sys.argv[1], sys.argv[2]) else 1
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
