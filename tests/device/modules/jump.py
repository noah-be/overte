#!/usr/bin/env python3
"""Exercise one device-independent jump and observe ascent and landing."""

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    before, airborne, landed = session.jump()
    gain = session._height(airborne) - session._height(before)
    delta = abs(session._height(landed) - session._height(before))
    print(f"Jump gained {gain:.3f} meters and landed within {delta:.3f} meters.")


module_main(main)
