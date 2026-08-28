#!/usr/bin/env python3
"""Approach the deterministic wall and verify that collision stops movement."""

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    before, after = session.assert_collision_wall()
    distance = (float(before["avatar"]["position"]["z"])
                - float(after["avatar"]["position"]["z"]))
    print(f"Collision wall stopped the avatar after {distance:.3f} meters.")


module_main(main)
