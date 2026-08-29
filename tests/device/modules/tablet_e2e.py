#!/usr/bin/env python3
"""Enforce a product policy through the semantic, platform-neutral tablet UI."""

from __future__ import annotations

import os
from pathlib import Path

from contracts import load_tablet_product_policy
from module_support import (AssertionFailure, InfrastructureError, assert_process,
                            fail, module_main, process_identity, write_json)
from overte_session import OverteSession


def load_policy() -> dict:
    value = os.environ.get("OVERTE_E2E_TABLET_POLICY", "")
    if not value:
        raise InfrastructureError("tablet-e2e requires --tablet-policy")
    try:
        return load_tablet_product_policy(Path(value))
    except (OSError, ValueError) as error:
        raise InfrastructureError(f"invalid tablet product policy: {error}") from error


def assert_policy(snapshot: dict, expectation: dict, screen_id: str,
                  evaluations: list[dict]) -> None:
    visible = set(snapshot["visibleControlIds"])
    required = set(expectation["requiredControlIds"])
    forbidden = set(expectation["forbiddenControlIds"])
    missing = sorted(required - visible)
    prohibited = sorted(forbidden & visible)
    evaluations.append({
        "forbiddenVisibleControlIds": prohibited,
        "missingRequiredControlIds": missing,
        "ready": snapshot["ready"],
        "screenId": screen_id,
    })
    if missing:
        fail(f"{screen_id} is missing required controls: {', '.join(missing)}")
    if prohibited:
        fail(f"{screen_id} exposes forbidden controls: {', '.join(prohibited)}")


def main() -> None:
    policy = load_policy()
    session = OverteSession()
    identity = process_identity()
    evaluations: list[dict] = []

    try:
        session.set_tablet(False)
        assert_process(identity, "defined closed tablet baseline")
        session.set_tablet(True)
        assert_process(identity, "probe-confirmed tablet open")

        home = session.wait_for_tablet_screen(
            "tablet.home", identity, "tablet-ui-home.json")
        assert_policy(home, policy["expectations"]["tablet.home"],
                      "tablet.home", evaluations)

        session.activate_tablet_control("app.settings", identity)
        settings_home = session.wait_for_tablet_screen(
            "settings.home", identity, "tablet-ui-settings-home.json")
        assert_policy(settings_home, policy["expectations"]["settings.home"],
                      "settings.home", evaluations)

        nested_screens = sorted(set(policy["expectations"]) - {
            "settings.home", "tablet.home"})
        for screen_id in nested_screens:
            expectation = policy["expectations"][screen_id]
            entry_control = expectation["entryControlId"]
            if entry_control not in settings_home["visibleControlIds"]:
                fail(f"settings.home cannot enter required policy screen {screen_id}")
            session.activate_tablet_control(entry_control, identity)
            snapshot = session.wait_for_tablet_screen(
                screen_id, identity, f"tablet-ui-{screen_id.replace('.', '-')}.json")
            assert_policy(snapshot, expectation, screen_id, evaluations)
            if "nav.back" not in snapshot["visibleControlIds"]:
                fail(f"{screen_id} does not expose nav.back")
            session.activate_tablet_control("nav.back", identity)
            settings_home = session.wait_for_tablet_screen(
                "settings.home", identity, "tablet-ui-settings-home-returned.json")
            assert_policy(settings_home, policy["expectations"]["settings.home"],
                          "settings.home", evaluations)

        if "nav.home" not in settings_home["visibleControlIds"]:
            fail("settings.home does not expose nav.home")
        session.activate_tablet_control("nav.home", identity)
        returned_home = session.wait_for_tablet_screen(
            "tablet.home", identity, "tablet-ui-home-returned.json")
        assert_policy(returned_home, policy["expectations"]["tablet.home"],
                      "tablet.home", evaluations)

        session.set_tablet(False)
        assert_process(identity, "probe-confirmed tablet close")
    except (AssertionFailure, InfrastructureError):
        write_json("tablet-policy-evaluation.json", {
            "contractVersion": policy["contractVersion"],
            "evaluations": evaluations,
            "profileId": policy["profileId"],
            "schemaVersion": 1,
        })
        raise

    write_json("tablet-policy-evaluation.json", {
        "contractVersion": policy["contractVersion"],
        "evaluations": evaluations,
        "profileId": policy["profileId"],
        "schemaVersion": 1,
    })
    print(f"Semantic tablet policy {policy['profileId']} passed in one process.")


module_main(main)
