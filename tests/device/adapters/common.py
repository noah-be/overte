#!/usr/bin/env python3
"""Small privacy-safe primitives shared by concrete device adapters."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import NoReturn


EMBEDDED_FIXTURE_URL = "overte-e2e://fixture/scene"


def arguments(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    return parser.parse_args()


def fail(message: str) -> NoReturn:
    raise RuntimeError(message)


def emit(value: object) -> None:
    print(json.dumps(value, separators=(",", ":"), sort_keys=True))


def parse_operation_arguments(value: str) -> dict:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        fail("operation arguments are not valid JSON")
    if not isinstance(payload, dict):
        fail("operation arguments must be a JSON object")
    return payload


def private_key(adapter_id: str, selector: str) -> str:
    return hashlib.sha256(f"{adapter_id}\0{selector}".encode()).hexdigest()[:24]


def state_directory(adapter_id: str, selector: str) -> Path:
    root = Path(os.environ.get(
        "OVERTE_DEVICE_STATE_ROOT",
        str(Path(tempfile.gettempdir()) / "overte-device-adapter-state"),
    )).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = root / private_key(adapter_id, selector)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def read_fresh_json(path: Path, maximum_age_seconds: float = 5.0) -> dict:
    last_error: Exception | None = None
    for _ in range(5):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return require_fresh_snapshot(value, maximum_age_seconds)
        except (OSError, json.JSONDecodeError, RuntimeError) as error:
            last_error = error
            time.sleep(0.05)
    fail(str(last_error) if last_error else "probe snapshot is unavailable")


def require_fresh_snapshot(value: object, maximum_age_seconds: float = 5.0) -> dict:
    """Reject cached probe evidence regardless of the concrete transport."""
    if not isinstance(value, dict):
        fail("probe snapshot is not a JSON object")
    sampled = value.get("sampleEpochMs")
    now = int(time.time() * 1000)
    if (not isinstance(sampled, int) or isinstance(sampled, bool)
            or abs(now - sampled) > maximum_age_seconds * 1000):
        fail("probe snapshot is stale")
    return value
