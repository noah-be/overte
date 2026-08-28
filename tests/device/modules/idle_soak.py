#!/usr/bin/env python3
"""Sample generic application and device health during a foreground soak."""

from __future__ import annotations

import json
import os
import time

from module_support import (ARTIFACT_DIR, advertised_capabilities, assert_foreground,
                            assert_process, contract_operation, fail, module_main, operation,
                            positive_integer_environment, wait_for_process, write_json)


def validated_telemetry(sample: dict) -> dict:
    expected = {
        "batteryLevel": (0, 100),
        "batteryTemperatureDeciC": (-500, 2000),
        "memoryPssKb": (1, 2 ** 63 - 1),
        "memoryRssKb": (1, 2 ** 63 - 1),
        "thermalStatus": (0, 6),
    }
    for field, (minimum, maximum) in expected.items():
        value = sample.get(field)
        if (not isinstance(value, int) or isinstance(value, bool)
                or not minimum <= value <= maximum):
            fail(f"telemetry field {field} is missing or invalid")
    return sample


def main() -> None:
    duration = positive_integer_environment("OVERTE_DEVICE_IDLE_SECONDS", 300, 7200)
    interval = positive_integer_environment("OVERTE_DEVICE_SAMPLE_SECONDS", 5, 300)
    try:
        max_thermal = int(os.environ.get("OVERTE_DEVICE_MAX_THERMAL_STATUS", "5"))
    except ValueError:
        fail("OVERTE_DEVICE_MAX_THERMAL_STATUS must be from 0 through 6")
    if max_thermal < 0 or max_thermal > 6:
        fail("OVERTE_DEVICE_MAX_THERMAL_STATUS must be from 0 through 6")
    telemetry_available = "telemetry.snapshot" in advertised_capabilities()
    contract_operation("app.launch")
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
        sample = (validated_telemetry(operation("telemetry.snapshot"))
                  if telemetry_available else {
                      "processRunning": True,
                      "foreground": True,
                      "telemetryAvailable": False,
                  })
        thermal = sample.get("thermalStatus")
        if isinstance(thermal, int) and thermal > max_thermal:
            fail(f"thermal status {thermal} exceeded safety limit {max_thermal}")
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
    evidence = "with device telemetry" if telemetry_available else "with process/foreground evidence"
    print(f"Application remained stable for {duration} seconds {evidence}.")


module_main(main)
