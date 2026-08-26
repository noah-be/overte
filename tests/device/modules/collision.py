#!/usr/bin/env python3
"""Approach the deterministic wall and verify that avatar collision stops movement."""

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    before, after = session.assert_collision_wall()
    distance = session.movement_projection(before, after, "forward")
    print(f"Collision wall stopped the avatar after {distance:.3f} meters.")


module_main(main)
