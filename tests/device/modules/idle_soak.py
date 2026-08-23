#!/usr/bin/env python3
"""Sample generic application and device health during a foreground soak."""

from __future__ import annotations

import json
import os
import time

from module_support import (ARTIFACT_DIR, assert_foreground, assert_process,
                            operation, positive_integer_environment, wait_for_process,
                            write_json)


duration = positive_integer_environment("OVERTE_DEVICE_IDLE_SECONDS", 300, 7200)
interval = positive_integer_environment("OVERTE_DEVICE_SAMPLE_SECONDS", 5, 300)
max_thermal = int(os.environ.get("OVERTE_DEVICE_MAX_THERMAL_STATUS", "5"))
if max_thermal < 0 or max_thermal > 6:
    raise RuntimeError("OVERTE_DEVICE_MAX_THERMAL_STATUS must be from 0 through 6")
operation("app.launch")
identity = wait_for_process()
assert_foreground("idle soak start")
started = time.monotonic()
samples = []
while True:
    elapsed = int(time.monotonic() - started)
    if elapsed >= duration:
        break
    assert_process(identity, f"idle soak after {elapsed}s")
    assert_foreground(f"idle soak after {elapsed}s")
    sample = operation("telemetry.snapshot")
    thermal = sample.get("thermalStatus")
    if isinstance(thermal, int) and thermal > max_thermal:
        raise RuntimeError(f"thermal status {thermal} exceeded safety limit {max_thermal}")
    sample["elapsedSeconds"] = elapsed
    samples.append(sample)
    time.sleep(min(interval, max(0, duration - elapsed)))
assert_process(identity, "idle soak completion")
assert_foreground("idle soak completion")
with (ARTIFACT_DIR / "telemetry.jsonl").open("w", encoding="utf-8") as output:
    for sample in samples:
        output.write(json.dumps(sample, sort_keys=True) + "\n")
write_json("metrics.json", {"durationSeconds": duration, "processIdentity": identity,
                             "samples": len(samples)})
print(f"Application remained stable for {duration} seconds.")
