#!/usr/bin/env python3
from module_support import operation, write_json
operation("app.launch"); state=operation("xr.focus")
if state.get("focused") is not True: raise RuntimeError("Overte does not hold Quest XR focus")
write_json("xr-focus.json",state); print("Quest XR focus is stable.")
