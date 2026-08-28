#!/usr/bin/env python3
"""Reload the deterministic fixture and verify it returns to ready state."""

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    before, after = OverteSession().reload_scene()
    print(f"Scene reloaded with {after['scene']['entityCount']} stable entities "
          f"after sample {before['sampleSequence']}.")


module_main(main)
