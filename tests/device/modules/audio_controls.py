#!/usr/bin/env python3
"""Verify the native mute control against in-client audio state."""

from __future__ import annotations

from module_support import assert_foreground, assert_process, module_main, process_identity
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    identity = process_identity()
    baseline, toggled, restored = session.assert_audio_mute_roundtrip()
    assert_process(identity, "audio mute roundtrip")
    assert_foreground("after audio mute roundtrip")
    print(f"Microphone mute changed {baseline} -> {toggled} -> {restored}.")


module_main(main)
