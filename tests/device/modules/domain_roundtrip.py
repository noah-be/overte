#!/usr/bin/env python3
"""Leave and re-enter the controlled domain without restarting Interface."""

from __future__ import annotations

from module_support import (assert_foreground, assert_process, fail, module_main,
                            process_identity, write_json)
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    identity = process_identity()
    connected_before = session.snapshot("roundtrip-domain-before.json")
    if connected_before["domain"]["connected"] is not True:
        fail("domain roundtrip did not start in a connected domain")

    serverless = session.load_controlled_scene()
    domain = serverless["domain"]
    if domain["connected"] is not False or domain["serverless"] is not True:
        fail("controlled serverless scene did not disconnect from the domain")
    assert_process(identity, "controlled domain departure")
    assert_foreground("controlled domain departure")
    write_json("roundtrip-serverless.json", serverless)

    reconnected, stable_samples = session.enter_controlled_domain()
    assert_process(identity, "controlled domain re-entry")
    assert_foreground("controlled domain re-entry")
    write_json("domain-roundtrip.json", {
        "processStable": True,
        "serverlessObserved": True,
        "stableReconnectSamples": len(stable_samples),
        "domainId": reconnected["domain"]["id"],
    })
    print(
        "Controlled domain roundtrip completed in one process with "
        f"{len(stable_samples)} stable reconnect samples."
    )


module_main(main)
