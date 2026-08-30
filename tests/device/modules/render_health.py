#!/usr/bin/env python3
"""Verify native presentation evidence plus in-client renderer progress."""

from __future__ import annotations

from module_support import assert_foreground, assert_process, module_main, process_identity
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    identity = process_identity()
    native, probe = session.assert_render_health()
    assert_process(identity, "render health")
    assert_foreground("after render health")
    print(
        f"Hardware renderer {native['backend']} presented a visible non-black surface; "
        f"probe frame count reached {probe['render']['frameCount']}."
    )


module_main(main)
