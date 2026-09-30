#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproducible, isolated Fedora x86_64 real Overte browser acceptance laboratory.

No system packages are installed, no existing domain settings are changed, and
all mutable state is kept under the repository's ignored build/browser-lab.
"""
import base64
import secrets
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

REPO = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
ROOT = REPO / "build/browser-lab"
CLIENT_NAME = "Overte-2026.04.1-x86_64.AppImage"
SERVER_NAME = "overte-server-2026.04.1.f91d15a-1.fc42.x86_64.rpm"
BASE_URL = "https://public.overte.org/build/overte/release/2026.04.1/"
ARTIFACTS = {
    CLIENT_NAME: "dc39f5b4694a1c48cfb1454a8922f6a25fa4db5820bf937113ebf4086aa99145",
    SERVER_NAME: "ecdabd358454b88dc669047fd1866b63114792280b331e48850a3c063464b2ae",
}
PERMISSION_KEYS = ["id_can_connect", "id_can_rez_avatar_entities", "id_can_adjust_locks", "id_can_rez", "id_can_rez_tmp",
                   "id_can_write_to_asset_server", "id_can_connect_past_max_capacity", "id_can_kick", "id_can_replace_content",
                   "id_can_get_and_set_private_user_data", "id_can_view_asset_urls"]
STATE = ROOT / "runtime/processes.json"


def run(args, **options):
    subprocess.run([str(a) for a in args], check=True, **options)


def extract_rpm(source):
    process = subprocess.Popen(["rpm2cpio", str(source)], stdout=subprocess.PIPE)
    destination = ROOT / ("server" if source.name == SERVER_NAME else "host-tools")
    destination.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["cpio", "-id", "--quiet", "-D", str(destination)], stdin=process.stdout)
    process.stdout.close()
    if result.returncode or process.wait():
        raise RuntimeError(f"Failed to extract {source.name}")


def prepare(client_artifact=None):
    for name in ["downloads", "server", "host-tools", "rpms", "logs", "runtime", "http", "config", "data", "evidence"]:
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    for name, expected in ARTIFACTS.items():
        target = ROOT / "downloads" / name
        if not target.exists():
            if name == CLIENT_NAME and client_artifact:
                shutil.copyfile(client_artifact, target)
            else:
                print(f"Downloading official {name}", flush=True)
                urllib.request.urlretrieve(BASE_URL + name, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != expected:
            raise RuntimeError(f"Artifact checksum differs from reviewed release: {name}")
    extract_rpm(ROOT / "downloads" / SERVER_NAME)
    appimage = ROOT / "downloads" / CLIENT_NAME
    appimage.chmod(0o755)
    if not (ROOT / "appimage/squashfs-root/AppRun").exists():
        (ROOT / "appimage").mkdir(exist_ok=True)
        with (ROOT / "logs/appimage-extract.log").open("w") as log:
            run([appimage, "--appimage-extract"], cwd=ROOT / "appimage", stdout=log)
    # Only official Fedora repositories; this downloads packages into the lab,
    # without installing services or replacing the desktop's PipeWire stack.
    if not (ROOT / "host-tools/usr/bin/Xvfb").exists() or not (ROOT / "host-tools/usr/bin/pulseaudio").exists():
        if not Path("/etc/fedora-release").exists():
            raise RuntimeError("This acceptance bootstrap is for Fedora x86_64. Provide Xvfb/PulseAudio on other hosts as documented.")
        run(["dnf", "download", "--repo=fedora", "--repo=updates", "--destdir", ROOT / "rpms",
             "xorg-x11-server-Xvfb.x86_64", "pulseaudio.x86_64", "pulseaudio-libs.x86_64", "speexdsp.x86_64"])
    for rpm in (ROOT / "rpms").glob("*.x86_64.rpm"):
        extract_rpm(rpm)
    run([sys.executable, SOURCE / "create-assets.py"])
    for filename in ["native-participant.js", "textured-cube.gltf", "checker.png"]:
        shutil.copyfile(SOURCE / filename, ROOT / "http" / filename)
    (ROOT / "http/command.json").write_text('{"sequence":0}\n')
    artifacts = [{"filename":name,"url":BASE_URL+name,"sha256":digest} for name,digest in ARTIFACTS.items()]
    artifacts.extend({"filename":rpm.name,"sha256":hashlib.sha256(rpm.read_bytes()).hexdigest()}
                     for rpm in (ROOT / "rpms").glob("*.x86_64.rpm"))
    (ROOT / "evidence/artifacts.json").write_text(json.dumps(artifacts, indent=2) + "\n")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "sine=frequency=440:sample_rate=48000", "-t", "5", "-ac", "1", ROOT / "evidence/browser-microphone.wav"])
    print("Prepared pinned release binaries and original real-world assets.")


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def start_ticks(pid):
    return Path(f"/proc/{pid}/stat").read_text().split(") ",1)[1].split()[19]


def launch(name, arguments, environment, state):
    with (ROOT / "logs" / f"{name}.log").open("w") as log:
        process = subprocess.Popen([str(a) for a in arguments], cwd=REPO,
                                   env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    state[name] = {"pid":process.pid,"startedAt":time.time(),"startTicks":start_ticks(process.pid),"arguments":[str(a) for a in arguments]}
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    time.sleep(0.2)
    if process.poll() is not None:
        raise RuntimeError(f"{name} exited; inspect {ROOT / 'logs' / (name+'.log')}")
    print(f"Started {name} (PID {process.pid})", flush=True)


def wait_port(port, seconds=20):
    for unused in range(seconds * 5):
        try:
            with socket.create_connection(("127.0.0.1",port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Local port {port} did not start")


def start(gateway=False):
    state = load_state()
    if any(alive(entry["pid"]) for entry in state.values()):
        raise RuntimeError("The managed lab is already running. Use status or stop first.")
    if not (ROOT / "appimage/squashfs-root/AppRun").exists():
        prepare()
    for port in [45100,45110] + ([8090] if gateway else []):
        probe = socket.socket()
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:
            probe.bind(("127.0.0.1",port))
        except OSError as error:
            raise RuntimeError(f"Port {port} is occupied; the lab will not replace another service") from error
        finally:
            probe.close()
    env = {**os.environ, "QT_QPA_PLATFORM":"xcb", "QT_SCALE_FACTOR":"1", "QT_AUTO_SCREEN_SCALE_FACTOR":"0"}
    app = ROOT / "appimage/squashfs-root"
    server = ROOT / "server/opt/overte"
    server_env = {**env, "LD_LIBRARY_PATH":f"{server}/lib:{app}/usr/lib",
                  "QT_PLUGIN_PATH":str(app / "usr/plugins"),
                  "XDG_CONFIG_HOME":str(ROOT / "config"),"XDG_DATA_HOME":str(ROOT / "data"),
                  "HIFI_DOMAIN_SERVER_HTTP_PORT":"45100","HIFI_DOMAIN_SERVER_HTTPS_PORT":"45101",
                  "HIFI_DOMAIN_SERVER_PORT":"45102","HIFI_DOMAIN_SERVER_DTLS_PORT":"45103"}
    admin_password = secrets.token_hex(32)
    admin_file = ROOT / "runtime/admin.json"
    admin_file.write_text(json.dumps({"username":"browser-lab-admin","password":admin_password})+"\n")
    admin_file.chmod(0o600)
    admin_authorization = "Basic " + base64.b64encode(("browser-lab-admin:"+admin_password).encode()).decode()
    permissions = {key:True for key in PERMISSION_KEYS}
    config = {"version":2.7,"metaverse":{"local_port":45102,"automatic_networking":"disabled","enable_packet_verification":True},
              "security":{"http_username":"browser-lab-admin","http_password":hashlib.sha256(admin_password.encode()).hexdigest(),
                          "allowed_subnets":["127.0.0.0/8"],"standard_permissions":[{"permissions_id":"localhost",**permissions},
                                                                                        {"permissions_id":"anonymous","id_can_connect":False}]},
              "authentication":{"enable_oauth2":False},"wizard":{"completed":True}}
    (ROOT / "config/domain.json").write_text(json.dumps(config,indent=2)+"\n")
    launch("domain",["unshare","--user","--map-current-user","--ipc","--",
                     server/"domain-server","--user-config",ROOT/"config/domain.json","--logOptions","nocolor,nojournald"],server_env,state)
    wait_port(45100)
    launch("assignments",[server/"assignment-client","-a","127.0.0.1","--server-port","45102",
                           "--disable-domain-port-auto-discovery","--min-listen-port","45200","--monitor-port","45290","-n","6",
                           "--logOptions","nocolor,nojournald"],server_env,state)
    shutil.copyfile(SOURCE/"native-participant.js",ROOT/"http/native-participant.js")
    (ROOT/"http/command.json").write_text('{"sequence":0}\n')
    launch("assets-http",[sys.executable,"-m","http.server","45110","--bind","127.0.0.1","--directory",ROOT/"http"],env,state)
    for number,name in [(94,"xvfb"),(95,"native-xvfb")]:
        if Path(f"/tmp/.X{number}-lock").exists():
            raise RuntimeError(f"Display :{number} is already in use; refusing to take it over")
        launch(name,[ROOT/"host-tools/usr/bin/Xvfb",f":{number}","-screen","0","1024x768x24","-nolisten","tcp"],env,state)
    for label in ["native","browser"]:
        script = ROOT / "runtime" / f"{label}.pa"
        script.write_text(f"load-module module-native-protocol-unix socket={ROOT}/runtime/{label}-pulse.sock auth-anonymous=1\n"
                          f"load-module module-null-sink sink_name={('lab' if label=='native' else 'browser')}_input rate=48000 channels=1\n"
                          f"load-module module-null-sink sink_name={('lab' if label=='native' else 'browser')}_output rate=48000 channels=2\n"
                          f"set-default-source {('lab' if label=='native' else 'browser')}_input.monitor\n"
                          f"set-default-sink {('lab' if label=='native' else 'browser')}_output\n")
        pulse_env = {**env,"DBUS_SESSION_BUS_ADDRESS":"unix:path=/dev/null"}
        launch(f"{label}-pulse",[SOURCE/"pulseaudio-local.sh","-n","--daemonize=no","--use-pid-file=no","--exit-idle-time=-1","-F",script],pulse_env,state)
    profile = ROOT / "client-script-profile"
    native_env = {**env,"DISPLAY":":95","PULSE_SERVER":f"unix:{ROOT}/runtime/native-pulse.sock",
                  "XDG_CONFIG_HOME":str(profile/"config"),"XDG_DATA_HOME":str(profile/"data"),"XDG_CACHE_HOME":str(profile/"cache")}
    config_path = profile / "config/Overte/Interface.json"
    config_path.parent.mkdir(parents=True,exist_ok=True)
    config_path.write_text(json.dumps({"Audio/mutedDesktop":True,"Audio/mutedHMD":True,
                                      "Audio/Desktop/INPUT":"lab_input.monitor","Audio/Desktop/OUTPUT":"lab_output"}))
    launch("native",[app/"AppRun","--url","hifi://127.0.0.2:45102/3,1.8,3/0,0,0,1","--allowMultipleInstances",
                     "--no-updater","--no-login-suggestion","--suppress-settings-reset","--displayName","Native-Lab-Participant",
                     "--disableDisplayPlugins","OpenXR,OpenVR","--defaultScriptsOverride","http://127.0.0.1:45110/native-participant.js"],native_env,state)
    # Provision using the local native author, then remove its extra privileges
    # before accepting any browser session. The native process stays initialized.
    for attempt in range(120):
        native_log = (ROOT / "logs/native.log").read_text(errors="replace")
        if '"kind":"asset-created"' in native_log and '"kind":"binary-asset-created"' in native_log:
            break
        if not alive(state["native"]["pid"]):
            raise RuntimeError("Native author exited during world provisioning")
        if attempt % 20 == 0:
            print("Waiting for actual domain scene and ATP asset upload...", flush=True)
        time.sleep(0.5)
    else:
        raise RuntimeError("Actual native ATP scene provisioning did not finish")
    guest = {key:key in ["id_can_connect","id_can_rez","id_can_rez_avatar_entities","id_can_view_asset_urls"] for key in PERMISSION_KEYS}
    groups = [{"permissions_id":name,**guest} for name in ["anonymous","localhost","logged-in","friends"]]
    request = urllib.request.Request("http://127.0.0.1:45100/settings.json",
        json.dumps({"security":{"standard_permissions":groups,"ip_permissions":[],"machine_fingerprint_permissions":[]},
                    "authentication":{"enable_oauth2":False}}).encode(),
        {"Content-Type":"application/json","Authorization":admin_authorization},method="POST")
    with urllib.request.urlopen(request) as response:
        if response.status != 200:
            raise RuntimeError("Failed to lower native author to anonymous guest baseline")
    saved = json.loads((ROOT / "config/domain.json").read_text())["security"]["standard_permissions"]
    if any(group.get(key) != guest[key] for group in saved for key in PERMISSION_KEYS):
        raise RuntimeError("Saved domain guest permissions did not match the intended baseline")
    policy = {"version":1,"mode":"anonymous-baseline","domains":[{"domain":"overte://127.0.0.2:45102",
               "settingsFile":str(ROOT/"config/domain.json")} ]}
    (ROOT / "config/guest-policy.json").write_text(json.dumps(policy,indent=2)+"\n")
    print("Provisioned actual scene; saved and verified anonymous guest permissions.",flush=True)
    if gateway:
        start_gateway(state)
    print("Lab domain hifi://127.0.0.2:45102; native display :95; browser http://127.0.0.1:8090 (with --gateway)")


def start_gateway(state):
    gateway_env = {**os.environ,"DISPLAY":":94","QT_QPA_PLATFORM":"xcb","QT_SCALE_FACTOR":"1","QT_AUTO_SCREEN_SCALE_FACTOR":"0",
                   "OVERTE_INTERFACE":str(ROOT/"appimage/squashfs-root/AppRun"),
                   "OVERTE_GATEWAY_DOMAINS":"overte://127.0.0.2:45102",
                   "OVERTE_GATEWAY_NATIVE_SCHEME":"hifi",
                   "OVERTE_GATEWAY_PULSEAUDIO":str(SOURCE/"pulseaudio-local.sh"),
                   "OVERTE_GATEWAY_GUEST_POLICY":str(ROOT/"config/guest-policy.json"),
                   "OVERTE_GATEWAY_ASSET_ORIGINS":"https://raw.githubusercontent.com,http://127.0.0.1:45110"}
    launch("gateway",["node",REPO/"browser-client/gateway/server.mjs"],gateway_env,state)
    wait_port(8090)


def stop(names=None):
    state=load_state()
    for name,entry in reversed(list(state.items())):
        if names is not None and name not in names:
            continue
        pid=entry["pid"]
        if not alive(pid):
            continue
        # Every spawned service gets its own process group and this marker in
        # its arguments or environment. Never operate on a reused arbitrary PID.
        try:
            command=Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0",b" ")
            working_directory=Path(f"/proc/{pid}/cwd").resolve()
        except (FileNotFoundError,PermissionError):
            continue
        if start_ticks(pid) != entry.get("startTicks"):
            raise RuntimeError(f"Stored PID for {name} was reused; refusing to stop another process")
        if str(REPO).encode() not in command and working_directory != REPO:
            raise RuntimeError(f"Stored PID for {name} belongs to another process; refusing to stop it")
        if os.getpgid(pid) != pid:
            raise RuntimeError(f"Process group for {name} changed; refusing to stop unrelated work")
        os.killpg(pid,signal.SIGTERM)
        for unused in range(15):
            if not alive(pid):break
            time.sleep(0.2)
        if alive(pid):os.killpg(pid,signal.SIGKILL)
        print(f"Stopped {name}")
    STATE.write_text(json.dumps({name:entry for name,entry in state.items() if names is not None and name not in names},indent=2)+"\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["prepare","start","stop","status","restart-gateway"])
    parser.add_argument("--client-artifact",type=Path)
    parser.add_argument("--gateway",action="store_true")
    parser.add_argument("--open-browser",action="store_true",help="Open the local browser interface after a successful managed start")
    args=parser.parse_args()
    if args.action=="prepare":prepare(args.client_artifact)
    elif args.action=="start":
        if args.open_browser and not args.gateway:parser.error("--open-browser requires --gateway")
        start(args.gateway)
        if args.open_browser:webbrowser.open("http://127.0.0.1:8090")
    elif args.action=="stop":stop()
    elif args.action=="restart-gateway":
        stop(["gateway"])
        start_gateway(load_state())
    else:
        print(json.dumps({name:{"pid":entry["pid"],"running":alive(entry["pid"])}for name,entry in load_state().items()},indent=2))


if __name__=="__main__":
    main()
