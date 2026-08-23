#!/usr/bin/env python3
from module_support import operation, write_json
result=operation("app.launch")
if result.get("launched") is not True: raise RuntimeError("devicectl did not confirm launch command completion")
write_json("launch.json",result);print("iOS launch command completed.")
