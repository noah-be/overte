#!/usr/bin/env python3
"""Exercise one target movement direction and observe matching displacement."""

from __future__ import annotations

import argparse

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=("backward", "forward", "left", "right"))
    direction = parser.parse_args().direction
    session = OverteSession()
    session.ensure_controlled_scene()
    before, after, _ = session.move(direction)
    projection = session.movement_projection(before, after, direction)
    print(f"Avatar moved {projection:.3f} meters {direction} after automated input.")


module_main(main)
