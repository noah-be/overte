#!/usr/bin/env python3
"""Interrupt the controlled domain stack and require automatic recovery."""

from __future__ import annotations

from module_support import assert_foreground, assert_process, module_main, process_identity
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    identity = process_identity()
    disconnected, reconnected = session.assert_network_fault_recovery()
    assert_process(identity, "network fault recovery")
    assert_foreground("after network fault recovery")
    print(
        "Controlled domain outage was observed and recovered in one process "
        f"({disconnected['domain']['protocol']} -> {reconnected['domain']['protocol']})."
    )


module_main(main)
