#!/usr/bin/env python3
"""Exercise repeated background/foreground transitions."""

from __future__ import annotations

import json
import os
import time

from module_support import (ARTIFACT_DIR, assert_foreground, assert_process,
                            operation, positive_integer_environment, wait_for_process,
                            write_json)


cycles = positive_integer_environment("OVERTE_DEVICE_LIFECYCLE_CYCLES", 10, 1000)
delay = positive_integer_environment("OVERTE_DEVICE_LIFECYCLE_DELAY_SECONDS", 2, 60)
operation("app.launch")
identity = wait_for_process()
records = []
for cycle in range(1, cycles + 1):
    operation("lifecycle.background")
    time.sleep(delay)
    assert_process(identity, f"cycle {cycle} background")
    if operation("app.foreground").get("foreground") is not False:
        raise RuntimeError(f"cycle {cycle}: application did not enter background")
    operation("app.launch")
    time.sleep(delay)
    assert_process(identity, f"cycle {cycle} foreground")
    assert_foreground(f"cycle {cycle}")
    records.append({"cycle": cycle, "completedEpoch": int(time.time())})
with (ARTIFACT_DIR / "cycles.jsonl").open("w", encoding="utf-8") as output:
    for record in records:
        output.write(json.dumps(record, sort_keys=True) + "\n")
write_json("metrics.json", {"cyclesCompleted": cycles, "processIdentity": identity})
print(f"Completed {cycles} lifecycle cycles without a process restart.")
