#!/usr/bin/env python3
"""Prove download, execution, and mutation by a controlled client entity script."""

from __future__ import annotations

from module_support import assert_foreground, assert_process, module_main, process_identity
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    identity = process_identity()
    before, after = session.scripted_entity_interaction()
    assert_process(identity, "scripted entity interaction")
    assert_foreground("after scripted entity interaction")
    print(
        "Controlled client entity script loaded and changed its own state "
        f"({before['activationCount']} -> {after['activationCount']})."
    )


module_main(main)
