#!/usr/bin/env python3
"""Stop and restart Overte while proving a new stable foreground process."""

import time

from module_support import (assert_foreground, assert_process, contract_operation, fail,
                            module_main, nonnegative_integer_environment, process_identity,
                            wait_for_process, wait_for_process_stopped, write_json)


def main() -> None:
    before = process_identity()
    contract_operation("app.stop")
    wait_for_process_stopped()
    contract_operation("app.launch")
    after = wait_for_process()
    if after == before:
        fail("application restart retained the old process identity")
    settle = nonnegative_integer_environment(
        "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS", 10, 60)
    time.sleep(settle)
    assert_process(after, "application restart")
    assert_foreground("application restart")
    write_json("restart.json", {
        "afterIdentity": after,
        "beforeIdentity": before,
        "settleSeconds": settle,
    })
    print("Application stopped and restarted with a new stable foreground process.")


module_main(main)
