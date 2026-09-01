#!/usr/bin/env python3
"""Force a loaded process crash and require a clean, usable recovery session."""

from __future__ import annotations

from module_support import (assert_foreground, contract_operation, fail, module_main,
                            process_identity, wait_for_process, wait_for_process_stopped,
                            write_json)
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    session.ensure_controlled_scene()
    contract_operation("tablet.open")
    before = process_identity()
    contract_operation("app.crash", {"mode": "abort"})
    wait_for_process_stopped()
    contract_operation("app.launch")
    after = wait_for_process()
    if after == before:
        fail("crash recovery reused the old process identity")
    assert_foreground("crash recovery")
    recovered = session.ensure_controlled_scene()
    contract_operation("tablet.open")
    contract_operation("tablet.close")
    write_json("crash-recovery.json", {
        "processChanged": True, "sceneReady": recovered["scene"]["ready"]})
    print("Loaded process crash recovered into a new usable scene and tablet session.")


module_main(main)
