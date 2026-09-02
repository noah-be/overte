#!/usr/bin/env python3
"""Exercise one loaded scene and tablet through background/foreground."""

from __future__ import annotations

from module_support import assert_foreground, assert_process, module_main, process_identity
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    identity = process_identity()
    before, after = session.assert_lifecycle_under_load()
    assert_process(identity, "lifecycle under load")
    assert_foreground("after lifecycle under load")
    print(
        "Loaded lifecycle retained scene, tablet, process, and renderer progress "
        f"({before['render']['frameCount']} -> {after['render']['frameCount']})."
    )


module_main(main)
