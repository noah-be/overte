#!/usr/bin/env python3
"""Verify controlled peer replication through local departure and reconnect."""

from __future__ import annotations

from module_support import assert_foreground, assert_process, module_main, process_identity
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    identity = process_identity()
    first, reconnected = session.assert_controlled_peer_roundtrip()
    assert_process(identity, "multi-user roundtrip")
    assert_foreground("after multi-user roundtrip")
    print(
        "Controlled peer remained identifiable and replicated movement across reconnect "
        f"({first['sessionId']} / {reconnected['observationCount']} observations)."
    )


module_main(main)
