#!/usr/bin/env python3
"""Shared helpers for platform-neutral device test modules."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Callable, NoReturn

from adapter_client import invoke


MANIFEST = Path(os.environ["OVERTE_DEVICE_ADAPTER_MANIFEST"])
TARGET = os.environ["OVERTE_DEVICE_TARGET_SELECTOR"]
ARTIFACT_DIR = Path(os.environ["OVERTE_DEVICE_ARTIFACT_DIR"])


class InfrastructureError(RuntimeError):
    """The target, transport or automation service was unavailable."""


class AssertionFailure(RuntimeError):
    """The application did not satisfy an observable E2E expectation."""


def operation(name: str, arguments: dict[str, object] | None = None) -> dict:
    try:
        value = invoke(MANIFEST, TARGET, name, arguments)
    except RuntimeError as error:
        detail = str(error)
        for prefix in ("ASSERTION: ", "error: ASSERTION: "):
            if detail.startswith(prefix):
                raise AssertionFailure(detail.removeprefix(prefix)) from error
        raise InfrastructureError(detail) from error
    except OSError as error:
        raise InfrastructureError(str(error)) from error
    if not isinstance(value, dict):
        raise InfrastructureError(f"adapter operation {name} did not return an object")
    return value


def fail(message: str) -> NoReturn:
    raise AssertionFailure(message)


def module_main(function: Callable[[], None]) -> None:
    """Give Jenkins a stable distinction between product and lab failures."""
    try:
        function()
    except InfrastructureError as error:
        print(f"INFRASTRUCTURE: {error}")
        raise SystemExit(75) from error
    except AssertionFailure as error:
        print(f"ASSERTION: {error}")
        raise SystemExit(1) from error
    except Exception as error:
        # A module bug or malformed lab configuration is an infrastructure
        # error, never evidence that the product failed its behavioral check.
        detail = str(error).replace(TARGET, "<target>")
        print(f"INFRASTRUCTURE: unexpected {type(error).__name__}: {detail}")
        raise SystemExit(75) from error


def positive_integer_environment(name: str, default: int, maximum: int) -> int:
    value = os.environ.get(name, str(default))
    if not value.isdigit() or int(value) <= 0 or int(value) > maximum:
        raise InfrastructureError(f"{name} must be an integer from 1 through {maximum}")
    return int(value)


def advertised_capabilities() -> set[str]:
    """Return the runner-attested operations available on this target."""
    try:
        value = json.loads(os.environ.get("OVERTE_DEVICE_CAPABILITIES_JSON", "[]"))
    except json.JSONDecodeError as error:
        raise InfrastructureError("runner capability context is invalid") from error
    if (not isinstance(value, list) or value != sorted(set(value))
            or not all(isinstance(item, str) and item for item in value)):
        raise InfrastructureError("runner capability context is invalid")
    return set(value)


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
