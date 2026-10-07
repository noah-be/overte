#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Own private software X11 and synthetic PulseAudio servers for short tests."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

from manage import REPO, ROOT, SOURCE, process_identity, owns_process

STATE = ROOT / "runtime/software-processes.json"
PRIVATE_TMP = ROOT / "runtime/tmp"
BROWSER_MICROPHONE = "browser_microphone"
BROWSER_REMAP_ARGUMENTS = ["source_name=" + BROWSER_MICROPHONE,
    "master=browser_input.monitor", "rate=48000", "channels=1",
    "master_channel_map=mono", "channel_map=mono", "remix=no",
    "source_properties=device.description=Overte_Direct_Synthetic_Microphone"]


def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def write_state(state: dict) -> None:
    temporary = STATE.with_suffix(".pending")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(STATE)


def children(pid: int) -> list[dict]:
    identities = []
    try:
        direct = (Path("/proc") / str(pid) / "task" / str(pid) / "children").read_text().split()
        for child in direct:
            identity = process_identity(int(child))
            if identity:
                identities.append(identity)
                identities.extend(children(int(child)))
    except OSError:
        pass
    return identities


def live(entry: dict) -> bool:
    return owns_process(entry["parent"]) or any(owns_process(child) for child in entry["children"])


def wait_path(path: Path, entry: dict) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists():
            return
        if not owns_process(entry["parent"]):
            break
        time.sleep(0.05)
    raise RuntimeError("An owned software server exited or did not create its private socket")


def launch(name: str, display: int, command: list[str], environment: dict, state: dict) -> None:
    with (ROOT / "logs" / f"{name}.log").open("w") as log:
        process = subprocess.Popen([sys.executable, str(SOURCE / "software-run.py"),
                                    "--display", str(display), "--", *command],
                                   cwd=REPO, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(0.3)
    identity = process_identity(process.pid)
    if identity is None or process.poll() is not None:
        raise RuntimeError(f"Own {name} exited during software startup; inspect its private log")
    state[name] = {"parent": identity, "children": children(process.pid), "display": display,
                   "xFiles": []}
    write_state(state)


def start() -> None:
    state = read_state()
    if any(live(entry) for entry in state.values()):
        raise RuntimeError("Own software laboratory is already running")
    for number in (104, 105):
        occupied = [Path(f"/tmp/.X{number}-lock"), Path(f"/tmp/.X11-unix/X{number}"),
                    PRIVATE_TMP / f".X{number}-lock", PRIVATE_TMP / f".X11-unix/X{number}"]
        if any(path.exists() for path in occupied):
            raise RuntimeError(f"Display :{number} is occupied; no existing display is changed")
    tools = ROOT / "host-tools/usr"
    for executable in (tools / "bin/Xvfb", tools / "bin/pulseaudio"):
        if not executable.is_file():
            raise RuntimeError("Prepare the pinned software tools first")
    for name in ("runtime", "logs"):
        (ROOT / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    authority = ROOT / "runtime/xauthority"
    authority.touch(mode=0o600)
    authority.chmod(0o600)
    commands = "".join(f"add :{number} . {secrets.token_hex(16)}\n" for number in (104, 105))
    subprocess.run(["xauth", "-f", str(authority), "-"], input=commands,
                   capture_output=True, text=True, check=True)
    environment = {**os.environ, "XAUTHORITY": str(authority),
                   "LD_LIBRARY_PATH": f"{tools}/lib64:{tools}/lib64/pulseaudio:{tools}/lib64/pulseaudio/modules"}
    state = {}
    try:
        for number in (104, 105):
            name = f"xvfb-{number}"
            launch(name, number, [str(tools / "bin/Xvfb"), f":{number}", "-screen", "0",
                                 "1024x768x24", "-nolisten", "tcp", "-auth", str(authority)], environment, state)
            for path in (PRIVATE_TMP / f".X{number}-lock", PRIVATE_TMP / f".X11-unix/X{number}"):
                wait_path(path, state[name])
                state[name]["xFiles"].append({"path": str(path), "inode": path.stat().st_ino})
            state[name]["children"] = children(state[name]["parent"]["pid"])
            write_state(state)
        for label, display in (("browser", 104), ("native", 105)):
            pulse = ROOT / "runtime" / f"{label}-pulse"
            pulse.mkdir(mode=0o700, exist_ok=True)
            pulse.chmod(0o700)
            script = pulse / "synthetic.pa"
            socket = ROOT / "runtime" / ("b.sock" if label == "browser" else "n.sock")
            if len(os.fsencode(socket)) >= 108:
                raise RuntimeError("Own PulseAudio Unix socket path is too long for this checkout")
            script.write_text(
                f"load-module module-native-protocol-unix socket={socket} auth-anonymous=1\n"
                f"load-module module-null-sink sink_name={label}_input rate=48000 channels=1\n"
                f"load-module module-null-sink sink_name={label}_output rate=48000 channels=2\n"
                + ("load-module module-remap-source " + " ".join(BROWSER_REMAP_ARGUMENTS) + "\n"
                   if label == "browser" else "")
                + f"set-default-source {BROWSER_MICROPHONE if label == 'browser' else label + '_input.monitor'}\n"
                + f"set-default-sink {label}_output\n")
            pulse_environment = {**environment, "PULSE_RUNTIME_PATH": str(pulse),
                                 "PULSE_STATE_PATH": str(pulse / "state"), "PULSE_COOKIE": str(pulse / "cookie")}
            launch(f"{label}-pulse", display, [str(tools / "bin/pulseaudio"), "-n", "--daemonize=no",
                   "--use-pid-file=no", "--exit-idle-time=-1", "--disable-shm=yes",
                   f"--dl-search-path={tools}/lib64/pulseaudio/modules", "-F", str(script)], pulse_environment, state)
            wait_path(socket, state[f"{label}-pulse"])
            state[f"{label}-pulse"]["children"] = children(state[f"{label}-pulse"]["parent"]["pid"])
            write_state(state)
        print(json.dumps({"started": True, "displays": [104, 105], "audio": "synthetic-null-sinks",
                          "gpuDevicesMounted": False, "processKinds": list(state)}))
    except BaseException:
        stop()
        raise


def prepare_browser_microphone() -> None:
    """Expose only the owned null monitor as a synthetic capture source."""
    browsers = ROOT / "runtime/browser-tests.json"
    if browsers.exists() and json.loads(browsers.read_text()):
        raise RuntimeError("Prepare the private microphone only between owned browser runs")
    entry = read_state().get("browser-pulse")
    if not entry or not owns_process(entry["parent"]) or not live(entry):
        raise RuntimeError("The exact owned browser Pulse server must be running")
    server = "unix:" + str(ROOT / "runtime/b.sock")
    def pactl(*arguments: str) -> str:
        return subprocess.check_output(["pactl", "--server=" + server, *arguments],
                                       text=True, timeout=5).strip()
    before = json.loads(pactl("--format=json", "list", "sources"))
    allowed = {"browser_input.monitor", "browser_output.monitor", BROWSER_MICROPHONE}
    if {source["name"] for source in before} - allowed:
        raise RuntimeError("The private Pulse server has an unexpected source; no source is changed")
    if not any(source["name"] == "browser_input.monitor" and source["driver"] == "module-null-sink.c"
               for source in before):
        raise RuntimeError("Require the owned null-sink master")
    module = None
    if not any(source["name"] == BROWSER_MICROPHONE for source in before):
        module = int(pactl("load-module", "module-remap-source", *BROWSER_REMAP_ARGUMENTS))
    after = json.loads(pactl("--format=json", "list", "sources"))
    source = next(item for item in after if item["name"] == BROWSER_MICROPHONE)
    if source["driver"] != "module-remap-source.c" or \
            source.get("properties", {}).get("device.master_device") != "browser_input.monitor":
        raise RuntimeError("The synthetic capture source does not match the owned master")
    pactl("set-default-source", BROWSER_MICROPHONE)
    if pactl("get-default-source") != BROWSER_MICROPHONE:
        raise RuntimeError("The private default capture source was not applied")
    proof = {"recordedUnixTime": time.time(), "pulseParentIdentity": entry["parent"],
             "moduleArguments": BROWSER_REMAP_ARGUMENTS, "loadedModuleIndex": module,
             "sourcesBefore": before, "sourcesAfter": after, "defaultSource": BROWSER_MICROPHONE,
             "sourceMaster": "browser_input.monitor", "physicalSourceAccessed": False,
             "chromeCaptureQualified": False, "note": "Pulse metadata alone does not prove Chrome capture"}
    path = ROOT / "runtime/browser-synthetic-microphone.json"
    path.write_text(json.dumps(proof, indent=2) + "\n")
    path.chmod(0o600)
    print(json.dumps({"syntheticSourcePrepared": True, "source": BROWSER_MICROPHONE,
                      "master": "browser_input.monitor", "physicalSourceAccessed": False}))


def stop() -> None:
    state = read_state()
    for name, entry in reversed(list(state.items())):
        targets = [*reversed(entry["children"]), entry["parent"]]
        for identity in targets:
            if owns_process(identity):
                try:
                    os.kill(identity["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 5
        while any(owns_process(identity) for identity in targets) and time.monotonic() < deadline:
            time.sleep(0.1)
        for identity in targets:
            if owns_process(identity):
                os.kill(identity["pid"], signal.SIGKILL)
        if any(owns_process(identity) for identity in targets):
            time.sleep(0.2)
        if any(owns_process(identity) for identity in targets):
            raise RuntimeError(f"Own {name} failed cleanup")
        for item in entry["xFiles"]:
            path = Path(item["path"])
            if path.exists() and path.stat().st_ino == item["inode"]:
                path.unlink()
        state.pop(name)
        write_state(state)
    print(json.dumps({"stopped": True, "remainingOwnedProcesses": len(state)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("start", "stop", "status", "prepare-browser-microphone"))
    args = parser.parse_args()
    (ROOT / "runtime").mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / "runtime/software-registry.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.operation == "start":
            start()
        elif args.operation == "stop":
            stop()
        elif args.operation == "prepare-browser-microphone":
            prepare_browser_microphone()
        else:
            print(json.dumps({name: {"alive": live(entry), "display": entry["display"]}
                              for name, entry in read_state().items()}))


if __name__ == "__main__":
    main()
