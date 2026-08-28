#!/usr/bin/env python3
"""Verify a deterministic grounded spawn in the controlled fixture."""

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    snapshot = session.assert_spawn_grounded()
    print(f"Avatar spawned grounded at y={snapshot['avatar']['position']['y']:.3f}.")


module_main(main)
