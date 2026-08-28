#!/usr/bin/env python3
"""Verify tablet-focused input cannot leak into avatar locomotion."""

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    session.assert_tablet_input_isolation()
    print("Tablet input remained isolated from world locomotion.")


module_main(main)
