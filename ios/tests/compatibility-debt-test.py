#!/usr/bin/env python3
"""Run and adversarially test the compatibility-debt inventory."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = IOS_ROOT.parent


def load_auditor():
    path = IOS_ROOT / "tools/audit-compatibility-debt.py"
    specification = importlib.util.spec_from_file_location("audit_compatibility_debt", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main() -> None:
    auditor = load_auditor()
    inventory = json.loads((IOS_ROOT / "compatibility-debt.json").read_text(encoding="utf-8"))
    counts = auditor.audit_inventory(SOURCE_ROOT, inventory)
    assert counts == {
        "qt5-cmake-api": 7,
        "qt6-removed-audio-api": 1,
        "core5compat-api": 12,
        "webengine-cpp-boundary": 12,
        "qt6-audio-runtime-semantics": 2,
        "apple-desktop-framework": 4,
        "apple-desktop-simd-flags": 1,
        "apple-desktop-neuron-sdk": 1,
        "ios-desktop-crashpad-handler": 1,
        "ios-audio-session-device-validation": 8,
        "ios-local-network-device-validation": 4,
        "dynamic-plugin-packaging": 2,
    }

    rules = {rule["id"]: rule for rule in inventory["rules"]}
    assert "Qt 5-only names remain isolated" in rules["qt6-removed-audio-api"]["exitCriterion"]
    audio_session_exit = rules["ios-audio-session-device-validation"]["exitCriterion"]
    assert "separately covers bootstrap and full-client activation" in audio_session_exit
    assert "compile-time bridge coverage is not device success" in audio_session_exit

    stale = deepcopy(inventory)
    stale["rules"][0]["files"].append("invented/Qt5Debt.cpp")
    try:
        auditor.audit_inventory(SOURCE_ROOT, stale)
    except ValueError as error:
        assert "removed=['invented/Qt5Debt.cpp']" in str(error)
    else:
        raise AssertionError("stale compatibility inventory was accepted")
    print("PASS iOS compatibility-debt tests")


if __name__ == "__main__":
    main()
