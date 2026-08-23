#!/usr/bin/env python3
"""Shared helpers for platform-neutral device test modules."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import NoReturn

from adapter_client import invoke


MANIFEST = Path(os.environ["OVERTE_DEVICE_ADAPTER_MANIFEST"])
TARGET = os.environ["OVERTE_DEVICE_TARGET_SELECTOR"]
ARTIFACT_DIR = Path(os.environ["OVERTE_DEVICE_ARTIFACT_DIR"])


def operation(name: str, arguments: dict[str, object] | None = None) -> dict:
    value = invoke(MANIFEST, TARGET, name, arguments)
    if not isinstance(value, dict):
        raise RuntimeError(f"adapter operation {name} did not return an object")
    return value


def fail(message: str) -> NoReturn:
    raise RuntimeError(message)


def positive_integer_environment(name: str, default: int, maximum: int) -> int:
    value = os.environ.get(name, str(default))
    if not value.isdigit() or int(value) <= 0 or int(value) > maximum:
        fail(f"{name} must be an integer from 1 through {maximum}")
    return int(value)


def process_identity() -> str:
    state = operation("app.process")
    identity = state.get("identity")
    if state.get("running") is not True or not isinstance(identity, str) or not identity:
        fail("application process is not running")
    return identity


def assert_process(identity: str, phase: str) -> None:
    observed = operation("app.process")
    if observed.get("running") is not True:
        fail(f"{phase}: application process exited")
    if observed.get("identity") != identity:
        fail(f"{phase}: application process restarted")


def wait_for_process(timeout_seconds: int = 30) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = operation("app.process")
        identity = state.get("identity")
        if state.get("running") is True and isinstance(identity, str) and identity:
            return identity
        time.sleep(1)
    fail("application process did not start")


def assert_foreground(phase: str) -> None:
    if operation("app.foreground").get("foreground") is not True:
        fail(f"{phase}: application is not foregrounded")


def write_json(name: str, value: object) -> None:
    (ARTIFACT_DIR / name).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
