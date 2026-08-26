#!/usr/bin/env python3
"""Exercise real movement input and observe avatar displacement in Overte."""

from __future__ import annotations

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    before, after = session.move()
    distance = session._distance(before["avatar"]["position"], after["avatar"]["position"])
    print(f"Avatar moved {distance:.3f} meters after automated input.")


module_main(main)
