#!/usr/bin/env python3
"""Deny and restore microphone permission while retaining a healthy app process."""

from __future__ import annotations

from module_support import (assert_foreground, assert_process, contract_operation, fail,
                            module_main, process_identity, write_json)


def main() -> None:
    identity = process_identity()
    baseline = contract_operation("permission.snapshot", {"permissionId": "microphone"})
    if baseline["state"] == "unknown":
        fail("microphone permission state is not observable")
    observations = [baseline]
    try:
        for requested in ("denied", "granted"):
            contract_operation("permission.set", {
                "permissionId": "microphone", "state": requested})
            observed = contract_operation(
                "permission.snapshot", {"permissionId": "microphone"})
            observations.append(observed)
            if observed["state"] != requested:
                fail(f"microphone permission did not become {requested}")
            assert_process(identity, f"microphone permission {requested}")
            assert_foreground(f"microphone permission {requested}")
    finally:
        if baseline["state"] in {"denied", "granted"}:
            contract_operation("permission.set", {
                "permissionId": "microphone", "state": baseline["state"]})
    write_json("permission-recovery.json", {"observations": observations,
                                             "restored": baseline["state"]})
    print("Microphone denial and grant recovery completed without a process restart.")


module_main(main)
