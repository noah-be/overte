#!/usr/bin/env python3
"""Mutate one domain entity through an independent actor and observe exact sync."""

from __future__ import annotations

from module_support import (assert_foreground, contract_operation, fail, module_main,
                            process_identity, assert_process, write_json)


def main() -> None:
    identity = process_identity()
    before = contract_operation("collaboration.snapshot")
    expected = "blue" if before["value"] != "blue" else "orange"
    contract_operation("collaboration.edit", {
        "entityName": before["entityName"], "value": expected})
    after = contract_operation("collaboration.snapshot")
    if after["entityName"] != before["entityName"]:
        fail("shared entity identity changed during synchronization")
    if after["value"] != expected or after["revision"] != before["revision"] + 1:
        fail("shared entity mutation was not observed exactly once")
    if after["actorId"] != "OVERTE_E2E_ACTOR_FIXTURE":
        fail("shared entity mutation did not originate from the controlled fixture actor")
    assert_process(identity, "entity synchronization")
    assert_foreground("entity synchronization")
    write_json("entity-sync.json", {"before": before, "after": after})
    print("Controlled entity mutation synchronized exactly once from the fixture actor.")


module_main(main)
