#!/usr/bin/env python3
"""Launch an application and verify a stable foreground process."""

from __future__ import annotations

import os
import time

from module_support import (assert_foreground, assert_process, module_main,
                            operation, wait_for_process, write_json)


def main() -> None:
    operation("app.launch")
    identity = wait_for_process()
    settle = int(os.environ.get("OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS", "10"))
    if settle < 0 or settle > 60:
        raise RuntimeError("OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS must be from 0 through 60")
    if (os.environ.get("OVERTE_ANDROID_E2E_DEBUG") == "1"
            and os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1"):
        # Pico can hand the foreground back to a late guardian/see-through
        # dialog after the Android activity initially reports as resumed.
        # Keep app.launch single-shot, but do not call it stable until that
        # delayed system transition window has elapsed.
        settle = max(settle, 25)
    time.sleep(settle)
    assert_process(identity, "launch smoke")
    assert_foreground("launch smoke")
    write_json("metrics.json", {"processIdentity": identity, "settleSeconds": settle})
    print("Application launch remained stable and foregrounded.")


module_main(main)
