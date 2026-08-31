#!/usr/bin/env python3
"""Verify Pico XR focus and Guardian state through the adapter contract."""

from module_support import operation, write_json

operation("app.launch")
state = operation("xr.focus")
if state.get("focused") is not True:
    raise RuntimeError("Overte does not hold XR focus")
if state.get("boundaryReady") is not True or state.get("seethroughActive") is True:
    raise RuntimeError("Pico Guardian or seethrough prevents stable XR execution")
write_json("xr-focus.json", state)
print("Pico XR focus is stable.")
