#!/usr/bin/env python3
"""Open and close the system tablet through the target automation layer."""

from __future__ import annotations

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    session.set_tablet(True)
    session.set_tablet(False)
    print("System tablet opened and closed with both transitions observed by Overte.")


module_main(main)
