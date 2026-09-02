#!/usr/bin/env python3
"""Upgrade between supplied builds and verify version and safe-state continuity."""

from __future__ import annotations

import os

from module_support import (assert_foreground, contract_operation, fail, module_main,
                            wait_for_process, write_json)
from overte_session import OverteSession


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"{name} is required")
    return value


def main() -> None:
    source = required("OVERTE_E2E_UPGRADE_FROM_VERSION")
    candidate = required("OVERTE_E2E_UPGRADE_TO_VERSION")
    source_artifact = required("OVERTE_E2E_UPGRADE_SOURCE_ARTIFACT")
    contract_operation("app.stop")
    contract_operation("app.install", {"path": source_artifact})
    contract_operation("app.launch")
    wait_for_process()
    assert_foreground("after source application installation")
    observed = contract_operation("app.version")
    if observed["version"] != source:
        fail("installed source version does not match the upgrade fixture")
    session = OverteSession()
    baseline = session.snapshot()["settings"]["audioWarnWhenMuted"]
    retained = not baseline
    contract_operation("setting.set", {
        "settingId": "audio.warn-when-muted", "enabled": retained})
    try:
        contract_operation("app.upgrade", {"fromVersion": source, "toVersion": candidate})
        wait_for_process()
        assert_foreground("after application upgrade")
        upgraded = contract_operation("app.version")
        if upgraded["version"] != candidate:
            fail("candidate version was not installed by the upgrade path")
        # The upgraded process owns a fresh monotonic probe sequence. Do not
        # carry the source process cursor across that lifecycle boundary.
        upgraded_session = OverteSession()
        if upgraded_session.snapshot()["settings"]["audioWarnWhenMuted"] != retained:
            fail("safe persisted setting was lost during application upgrade")
    finally:
        contract_operation("setting.set", {
            "settingId": "audio.warn-when-muted", "enabled": baseline})
    write_json("upgrade.json", {"fromVersion": source, "toVersion": candidate,
                                 "sourceInstalled": True,
                                 "safeSettingRetained": True})
    print(f"Application upgraded from {source} to {candidate} with safe state retained.")


module_main(main)
