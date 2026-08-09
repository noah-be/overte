#!/usr/bin/env python3
"""Select an available simulator from the newest installed iOS runtime."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from typing import Any


IOS_RUNTIME_PATTERN = re.compile(r"\.iOS-([0-9]+(?:-[0-9]+)*)$")


def ios_runtime_version(runtime: str) -> tuple[int, ...] | None:
    match = IOS_RUNTIME_PATTERN.search(runtime)
    return tuple(map(int, match.group(1).split("-"))) if match else None


def select_device(payload: Mapping[str, Any], family: str) -> str:
    runtimes: list[tuple[tuple[int, ...], str, list[Mapping[str, Any]]]] = []
    for runtime, devices in payload.get("devices", {}).items():
        version = ios_runtime_version(runtime)
        if version is not None:
            runtimes.append((version, runtime, devices))

    for _version, _runtime, devices in sorted(runtimes, reverse=True):
        matching = sorted(
            (
                device
                for device in devices
                if device.get("isAvailable")
                and family.lower() in str(device.get("name", "")).lower()
            ),
            key=lambda device: (str(device.get("name", "")), str(device.get("udid", ""))),
        )
        if matching:
            udid = matching[0].get("udid")
            if isinstance(udid, str) and udid:
                return udid
    raise LookupError(f"no available {family.lower()} simulator")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1].lower() not in {"iphone", "ipad"}:
        print(f"usage: {sys.argv[0]} iphone|ipad", file=sys.stderr)
        return 2
    try:
        print(select_device(json.load(sys.stdin), sys.argv[1]))
    except (json.JSONDecodeError, LookupError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
