#!/usr/bin/env python3
"""Exercise bounded device-independent flight and observe active ascent."""

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    before, flying = session.fly()
    events = flying["verticalEvents"]
    gain = events["lastFlightPeakY"] - events["lastFlightStartY"]
    print(f"Active flight gained {gain:.3f} meters.")


module_main(main)
