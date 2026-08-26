#!/usr/bin/env python3
"""Exercise a real target look gesture and observe the resulting camera rotation."""

from __future__ import annotations

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    before, after = session.look()
    delta = session._angle_delta(before["view"]["orientation"], after["view"]["orientation"])
    print(f"View orientation changed by {delta:.2f} degrees after automated input.")


module_main(main)
