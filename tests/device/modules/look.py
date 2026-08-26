#!/usr/bin/env python3
"""Exercise a real target look gesture and observe the resulting camera rotation."""

from __future__ import annotations

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    _before, _after, delta = session.look()
    print(f"OpenXR view input was consumed at {delta:.2f} degrees with neutral controllers.")


module_main(main)
