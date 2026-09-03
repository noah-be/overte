#!/usr/bin/env python3
"""Verify one native Unicode editing flow without leaking input to the world."""

from __future__ import annotations

from module_support import (assert_foreground, assert_process, fail, module_main,
                            process_identity, write_json)
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    identity = process_identity()
    assert_foreground("before text input")
    world_before = session.snapshot("text-world-before.json")
    session.focus_text_input()
    empty = session.text_snapshot()
    write_json("text-focused.json", empty)
    if empty["value"] or empty["focused"] is not True:
        fail("controlled text field was not focused and cleared")

    source = "Overte E2E äöüX"
    expected = source[:-1]
    session.type_text(source, backspace_count=1, submit=True)
    entered = session.wait_for_text(
        lambda value: value["value"] == expected
        and value["submittedCount"] == empty["submittedCount"] + 1,
        "edited Unicode text and one submit event",
    )
    write_json("text-submitted.json", entered)

    session.dismiss_text_input()
    dismissed = session.wait_for_text(
        lambda value: value["focused"] is False
        and value["keyboardVisible"] is not True,
        "text focus and platform keyboard to be dismissed",
    )
    write_json("text-dismissed.json", dismissed)
    world_after = session.snapshot("text-world-after.json")
    maximum_drift = session._float_environment(
        "OVERTE_E2E_MAX_TEXT_WORLD_DRIFT_METERS", 0.08, 0.001, 1.0)
    if session._planar_distance(world_before["avatar"]["position"],
                                world_after["avatar"]["position"]) > maximum_drift:
        fail("text input leaked into world locomotion")
    assert_process(identity, "text input")
    assert_foreground("after text input")
    print("Native Unicode editing, submit, dismissal, and world isolation passed.")


module_main(main)
