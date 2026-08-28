#!/usr/bin/env python3
"""Launch an application and verify a stable foreground process."""

from __future__ import annotations

import time

from module_support import (assert_foreground, assert_process, contract_operation,
                            module_main, nonnegative_integer_environment,
                            wait_for_process, write_json)


def main() -> None:
    contract_operation("app.launch")
    identity = wait_for_process()
    settle = nonnegative_integer_environment(
        "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS", 10, 60)
    time.sleep(settle)
    assert_process(identity, "launch smoke")
    assert_foreground("launch smoke")
    write_json("metrics.json", {"processIdentity": identity, "settleSeconds": settle})
    print("Application launch remained stable and foregrounded.")


module_main(main)
