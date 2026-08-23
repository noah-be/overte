#!/usr/bin/env python3
"""Launch an application and verify a stable foreground process."""

from __future__ import annotations

import os
import time

from module_support import assert_foreground, assert_process, operation, wait_for_process, write_json


operation("app.launch")
identity = wait_for_process()
settle = int(os.environ.get("OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS", "10"))
if settle < 0 or settle > 60:
    raise RuntimeError("OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS must be from 0 through 60")
time.sleep(settle)
assert_process(identity, "launch smoke")
assert_foreground("launch smoke")
write_json("metrics.json", {"processIdentity": identity, "settleSeconds": settle})
print("Application launch remained stable and foregrounded.")
