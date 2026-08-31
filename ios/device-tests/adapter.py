#!/usr/bin/env python3
"""Universal device-harness adapter for physical iOS and iPadOS devices."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

BUNDLE_ID=os.environ.get("OVERTE_IOS_BUNDLE_ID","org.overte.interface.dev")
CAPABILITIES=sorted({"app.launch","app.stop"})

def xcrun():
    override=os.environ.get("OVERTE_APPLE_XCRUN")
    if override: return override
    found=shutil.which("xcrun")
    if not found: raise RuntimeError("xcrun is unavailable")
    return found
def available():
    try: xcrun(); return True
    except RuntimeError: return False
def command_json(args,timeout=60):
    with tempfile.TemporaryDirectory(prefix="overte-devicectl-") as d:
        output=Path(d)/"result.json"
        result=subprocess.run([xcrun(),"devicectl",*args,"--quiet","--timeout",str(timeout),"--json-output",str(output)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout+5,check=False)
        if result.returncode!=0 or not output.is_file(): raise RuntimeError("devicectl operation failed")
        return json.loads(output.read_text(encoding="utf-8"))
def device_records():
    if not available(): return []
    payload=command_json(["list","devices"]); devices=payload.get("result",{}).get("devices",[])
    return devices if isinstance(devices,list) else []
def eligible(record):
    connection=record.get("connectionProperties",{}); device=record.get("deviceProperties",{}); hardware=record.get("hardwareProperties",{})
    return (isinstance(record.get("identifier"),str) and connection.get("tunnelState")=="connected" and connection.get("pairingState")=="paired" and device.get("developerModeStatus")=="enabled" and device.get("ddiServicesAvailable") is True and hardware.get("deviceType") in {"iPhone","iPad"})
def discover():
    found=[]
    for r in device_records():
        if eligible(r):
            h=r.get("hardwareProperties",{}); found.append({"selector":r["identifier"],"displayName":h.get("marketingName") or h.get("deviceType") or "Apple mobile device","platform":"ios","physical":True,"capabilities":CAPABILITIES})
    return found
def record_for(target):
    for r in device_records():
        if r.get("identifier")==target and eligible(r): return r
    raise RuntimeError("target is not a paired physical iOS device in developer mode")
def describe(target):
    r=record_for(target); d=r.get("deviceProperties",{}); h=r.get("hardwareProperties",{})
    return {"deviceType":h.get("deviceType"),"model":h.get("marketingName") or h.get("productType"),"osVersion":d.get("osVersionNumber"),"physical":True,"platform":"ios"}
def invoke(target,operation):
    record_for(target)
    if operation=="app.launch": command_json(["device","process","launch","--device",target,"--terminate-existing",BUNDLE_ID]); return {"launched":True}
    if operation=="app.stop": command_json(["device","process","terminate","--device",target,BUNDLE_ID]); return {"stopped":True}
    raise RuntimeError("unsupported adapter operation")
def cleanup(target):
    try: invoke(target,"app.stop")
    except RuntimeError: pass
    return {"cleaned":True}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("action",choices=("discover","describe","invoke","cleanup"));p.add_argument("--target");p.add_argument("--operation");p.add_argument("--arguments",default="{}");a=p.parse_args()
    if a.action=="discover": value=discover()
    elif not a.target: raise ValueError("--target is required")
    elif a.action=="describe": value=describe(a.target)
    elif a.action=="cleanup": value=cleanup(a.target)
    elif not a.operation: raise ValueError("--operation is required")
    elif not isinstance(json.loads(a.arguments),dict): raise ValueError("--arguments must be a JSON object")
    else:value=invoke(a.target,a.operation)
    print(json.dumps(value,sort_keys=True,separators=(",",":")));return 0
if __name__=="__main__":
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);raise SystemExit(2)
