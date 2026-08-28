#!/usr/bin/env python3
"""Exercise real movement input and observe avatar displacement in Overte."""

from __future__ import annotations

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    distances = {}
    for direction in ("forward", "backward", "left", "right"):
        before, after, _ = session.move(direction)
        distances[direction] = session.movement_projection(before, after, direction)
    summary = ", ".join(
        f"{direction}={distance:.3f}" for direction, distance in distances.items())
    print(f"Body-relative movement observed in every direction: {summary} meters.")


module_main(main)
