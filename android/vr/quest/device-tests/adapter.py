#!/usr/bin/env python3
"""Universal device-harness adapter for physical Meta Quest headsets."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]; sys.path.insert(0,str(ROOT))
from android.common.device_tests.adb_transport import AdbTransport  # noqa: E402
PACKAGE="io.highfidelity.questInterface"; LAUNCHER=f"{PACKAGE}/.InterfaceActivity"
CAPABILITIES=sorted({"app.foreground","app.launch","app.process","app.stop","telemetry.snapshot","xr.focus"})
ADB=AdbTransport()
def is_quest(t):
    identity=" ".join(ADB.prop(t,k) for k in ("ro.product.manufacturer","ro.product.brand","ro.product.model","ro.product.device")).lower()
    return ADB.prop(t,"ro.kernel.qemu")!="1" and any(x in identity for x in ("oculus","quest","meta")) and "arm64-v8a" in ADB.prop(t,"ro.product.cpu.abilist").split(",")
def require(t):
    if t not in ADB.authorized_targets() or not is_quest(t): raise RuntimeError("target is not an authorized physical Quest headset")
def discover():
    return [{"selector":t,"displayName":ADB.prop(t,"ro.product.model") or "Quest","platform":"android-vr-quest","physical":True,"capabilities":CAPABILITIES} for t in ADB.authorized_targets() if is_quest(t)]
def describe(t):
    require(t); return {"abi":ADB.prop(t,"ro.product.cpu.abilist").split(",")[0],"androidSdk":int(ADB.prop(t,"ro.build.version.sdk")),"manufacturer":ADB.prop(t,"ro.product.manufacturer"),"model":ADB.prop(t,"ro.product.model"),"physical":True,"platform":"android-vr-quest"}
def invoke(t,op):
    ADB.require_connected(t)
    if op=="app.launch": ADB.shell(t,"am","start","-W","-n",LAUNCHER); return {"launched":True}
    if op=="app.stop": ADB.shell(t,"am","force-stop",PACKAGE); return {"stopped":True}
    if op=="app.process": return ADB.process_state(t,PACKAGE)
    if op=="app.foreground": return {"foreground":ADB.foreground_package(t)==PACKAGE}
    if op=="telemetry.snapshot": return ADB.telemetry_snapshot(t,PACKAGE)
    if op=="xr.focus": return {"focused":ADB.foreground_package(t)==PACKAGE}
    raise RuntimeError("unsupported adapter operation")
def cleanup(t): ADB.require_connected(t); ADB.shell(t,"am","force-stop",PACKAGE,check=False); return {"cleaned":True}
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("action",choices=("discover","describe","invoke","cleanup")); p.add_argument("--target"); p.add_argument("--operation"); p.add_argument("--arguments",default="{}"); a=p.parse_args()
    if a.action=="discover": value=discover()
    elif not a.target: raise ValueError("--target is required")
    elif a.action=="describe": value=describe(a.target)
    elif a.action=="cleanup": value=cleanup(a.target)
    elif not a.operation: raise ValueError("--operation is required")
    elif not isinstance(json.loads(a.arguments),dict): raise ValueError("--arguments must be a JSON object")
    else: value=invoke(a.target,a.operation)
    print(json.dumps(value,sort_keys=True,separators=(",",":"))); return 0
if __name__=="__main__":
    try: raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError) as e: print(f"error: {e}",file=sys.stderr); raise SystemExit(2)
