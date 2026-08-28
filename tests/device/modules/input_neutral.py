#!/usr/bin/env python3
"""Verify that bounded emulated inputs leave no stuck world or view input."""

from module_support import module_main
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    snapshot = session.input_neutral_snapshot()
    print(f"Input became neutral at sample {snapshot['sampleSequence']}.")


module_main(main)
