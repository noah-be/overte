#!/usr/bin/env python3
"""Activate one controlled world entity through the target's primary input."""

from __future__ import annotations

from module_support import assert_foreground, assert_process, module_main, process_identity
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    identity = process_identity()
    assert_foreground("before world interaction")
    before, after = session.primary_interaction()
    assert_process(identity, "world interaction")
    assert_foreground("after world interaction")
    observed = after["interaction"]
    print(
        "Controlled world target received exactly one primary interaction "
        f"({before['interaction']['pressCount']} -> {observed['pressCount']})."
    )


module_main(main)
