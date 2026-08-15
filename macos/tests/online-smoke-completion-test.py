#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "macos/tools/validate-online-smoke-completion.py"
SPEC = importlib.util.spec_from_file_location("validate_online_completion", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def completion(success: bool = True) -> dict:
    return {
        "schema_version": 1,
        "ready_for_external_validation": success,
        "script_success": success,
    }


def process(*, controlled: bool) -> dict:
    return {
        "exit_code": -15 if controlled else 0,
        "timed_out": False,
        "completion_file_observed": True,
        "terminated_after_completion": controlled,
        "sent_sigterm": controlled,
    }


assert MODULE.validate(completion(), process(controlled=False))["process_mode"] == "natural-exit"
assert MODULE.validate(completion(), process(controlled=True))["process_mode"] == "controlled-completion"

invalid_cases = []
invalid_cases.append(({**completion(), "extra": True}, process(controlled=False)))
invalid_cases.append((completion(False), process(controlled=False)))
invalid_cases.append((completion(), {**process(controlled=False), "timed_out": True}))
invalid_cases.append((completion(), {**process(controlled=False), "completion_file_observed": False}))
invalid_cases.append((completion(), {**process(controlled=False), "exit_code": -11}))
invalid_cases.append((completion(), {**process(controlled=True), "sent_sigterm": False}))
for completion_value, process_value in invalid_cases:
    try:
        MODULE.validate(completion_value, process_value)
    except MODULE.ValidationError:
        pass
    else:
        raise AssertionError("invalid online completion evidence was accepted")

print("macOS online completion validator contract valid")
