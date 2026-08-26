#!/usr/bin/env python3
"""Exercise one signed target look direction and observe matching camera rotation."""

from __future__ import annotations

import argparse

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=("down", "left", "right", "up"))
    direction = parser.parse_args().direction
    session = OverteSession()
    session.ensure_controlled_scene()
    before, after, _ = session.look(direction)
    delta = session._angle_delta(
        before["view"]["orientation"], after["view"]["orientation"])
    print(f"View turned {direction} by {delta:.2f} degrees after automated input.")


module_main(main)
