#!/usr/bin/env python3
"""Universal device-harness adapter for the local physical macOS host."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, signal, subprocess, sys, tempfile, time
from pathlib import Path

def enabled(): return sys.platform=="darwin" or os.environ.get("OVERTE_MACOS_ALLOW_NON_DARWIN")=="1"
def executable(): return Path(os.environ.get("OVERTE_MACOS_EXECUTABLE","/Applications/interface.app/Contents/MacOS/interface"))
def selector(): return "local-"+hashlib.sha256(platform.node().encode()).hexdigest()[:20]
def state_path(): return Path(tempfile.gettempdir())/("overte-macos-device-"+hashlib.sha256(selector().encode()).hexdigest()[:20]+".json")
def capabilities(): return sorted({"app.launch","app.process","app.stop","telemetry.snapshot"}) if executable().is_file() and os.access(executable(),os.X_OK) else []
def discover(): return [] if not enabled() else [{"selector":selector(),"displayName":"Local Mac","platform":"macos","physical":True,"capabilities":capabilities()}]
def require(target):
    if not enabled() or target!=selector(): raise RuntimeError("target is not the local physical macOS host")
def describe(target):
    require(target)
    model="unknown"
    try:model=subprocess.run(["sysctl","-n","hw.model"],text=True,capture_output=True,timeout=5).stdout.strip() or "unknown"
    except OSError:pass
    return {"architecture":platform.machine(),"model":model,"osVersion":platform.mac_ver()[0] or platform.release(),"physical":True,"platform":"macos"}
def read_state():
    try:return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):return {}
def process_state():
    state=read_state();pid=state.get("pid");identity=state.get("identity")
    if not isinstance(pid,int) or not isinstance(identity,str):return {"running":False,"identity":None}
    try:os.kill(pid,0)
    except OSError:return {"running":False,"identity":None}
    return {"running":True,"identity":identity}
def launch():
    if not capabilities(): raise RuntimeError("configured macOS Overte executable is unavailable")
    current=process_state()
    if current["running"]: return {"launched":True}
    process=subprocess.Popen([str(executable())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    identity=f"{process.pid}:{time.time_ns()}";state_path().write_text(json.dumps({"pid":process.pid,"identity":identity}),encoding="utf-8")
    return {"launched":True}
def stop():
    state=read_state();pid=state.get("pid")
    if isinstance(pid,int):
        try:os.killpg(pid,signal.SIGTERM)
        except OSError:pass
    try:state_path().unlink()
    except FileNotFoundError:pass
    return {"stopped":True}
def telemetry():
    state=read_state();pid=state.get("pid")
    if not isinstance(pid,int):return {"memoryRssKb":None,"cpuPercent":None}
    result=subprocess.run(["ps","-o","rss=,%cpu=","-p",str(pid)],text=True,capture_output=True,timeout=5)
    fields=result.stdout.split();return {"memoryRssKb":int(fields[0]) if fields else None,"cpuPercent":float(fields[1]) if len(fields)>1 else None}
def invoke(target,op):
    require(target)
    if op=="app.launch":return launch()
    if op=="app.stop":return stop()
    if op=="app.process":return process_state()
    if op=="telemetry.snapshot":return telemetry()
    raise RuntimeError("unsupported adapter operation")
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("action",choices=("discover","describe","invoke","cleanup"));p.add_argument("--target");p.add_argument("--operation");p.add_argument("--arguments",default="{}");a=p.parse_args()
    if a.action=="discover":value=discover()
    elif not a.target:raise ValueError("--target is required")
    elif a.action=="describe":value=describe(a.target)
    elif a.action=="cleanup":require(a.target);value=stop()|{"cleaned":True}
    elif not a.operation:raise ValueError("--operation is required")
    elif not isinstance(json.loads(a.arguments),dict):raise ValueError("--arguments must be a JSON object")
    else:value=invoke(a.target,a.operation)
    print(json.dumps(value,sort_keys=True,separators=(",",":")));return 0
if __name__=="__main__":
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired,json.JSONDecodeError) as e:print(f"error: {e}",file=sys.stderr);raise SystemExit(2)
