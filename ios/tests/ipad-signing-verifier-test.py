#!/usr/bin/env python3
"""Offline profile/entitlement contracts for signed iPad candidates."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "ci/verify-ipad-signing.py"
SPEC = importlib.util.spec_from_file_location("ipad_signing", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

TEAM = "TESTTEAM42"
BUNDLE = "org.overte.interface.dev"
APPLICATION = f"{TEAM}.{BUNDLE}"
DEVICE = "00008110-001234567890001E"
NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def fixtures() -> tuple[dict, dict, dict]:
    profile = {
        "TeamIdentifier": [TEAM],
        "ExpirationDate": NOW + dt.timedelta(days=30),
        "ProvisionedDevices": [DEVICE],
        "Entitlements": {"application-identifier": APPLICATION, "get-task-allow": True},
    }
    signature = {
        "application-identifier": APPLICATION,
        "com.apple.developer.team-identifier": TEAM,
        "get-task-allow": True,
    }
    info = {"CFBundleIdentifier": BUNDLE}
    return profile, signature, info


def expect_failure(mutation, expected: str) -> None:
    profile, signature, info = fixtures()
    mutation(profile, signature, info)
    try:
        MODULE.validate_metadata(profile, signature, info, BUNDLE, APPLICATION, DEVICE, NOW)
    except ValueError as error:
        assert expected in str(error), (expected, str(error))
    else:
        raise AssertionError(f"unsafe signing metadata accepted: {expected}")


profile, signature, info = fixtures()
MODULE.validate_metadata(profile, signature, info, BUNDLE, APPLICATION, DEVICE, NOW)
expect_failure(lambda p, s, i: s.update({"application-identifier": f"OTHER.{BUNDLE}"}), "signature application")
expect_failure(lambda p, s, i: p["Entitlements"].update({"get-task-allow": False}), "get-task-allow")
expect_failure(lambda p, s, i: p.update({"ExpirationDate": NOW}), "expired")
expect_failure(lambda p, s, i: p.update({"ProvisionedDevices": ["other-device"]}), "authorize")
expect_failure(lambda p, s, i: i.update({"CFBundleIdentifier": "org.example.other"}), "bundle identifier")

profile, signature, info = fixtures()
profile.pop("ProvisionedDevices")
profile["ProvisionsAllDevices"] = True
MODULE.validate_metadata(profile, signature, info, BUNDLE, APPLICATION, DEVICE, NOW)

print("PASS signed iPad profile and entitlement verifier contracts")
