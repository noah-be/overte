#!/usr/bin/env python3
"""Load the controlled scene and verify the in-client probe reaches ready state."""

from __future__ import annotations

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    snapshot = OverteSession().ensure_controlled_scene()
    print(f"Controlled scene became ready with {snapshot['scene']['entityCount']} entities.")


module_main(main)
