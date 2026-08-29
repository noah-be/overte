#!/usr/bin/env python3
"""Exercise a real target look gesture and observe the resulting camera rotation."""

from __future__ import annotations

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    deltas = {}
    for direction in ("left", "right", "up", "down"):
        before, after, _ = session.look(direction)
        deltas[direction] = session.look_direction_delta(before, after, direction)
    summary = ", ".join(f"{direction}={delta:.2f}" for direction, delta in deltas.items())
    print(f"Signed view rotations observed in every direction: {summary} degrees.")


module_main(main)
