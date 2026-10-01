#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproducible, isolated x86_64 real Overte browser acceptance laboratory.

No system packages are installed, no existing domain settings are changed, and
all mutable state is kept under the repository's ignored build/browser-lab.
"""
import base64
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
from native_admin import native_admin_credential
from guest_permissions import guest_permission_diagnostics
from provisioning_diagnostics import post_guest_settings, ProvisioningDiagnosticError
from host_tools import select_tools, load_tools, preflight, tool_identities

REPO = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("OVERTE_LAB_ROOT", str(REPO / "build/browser-lab")))
if not ROOT.is_absolute() or ROOT.resolve() in (Path('/'), Path.home(), REPO, Path('/tmp')):
    raise RuntimeError("OVERTE_LAB_ROOT must select a dedicated absolute laboratory directory")
ROOT = ROOT.resolve()
CLIENT_NAME = "Overte-2026.04.1-x86_64.AppImage"
SERVER_NAME = "overte-server-2026.04.1.f91d15a-1.fc42.x86_64.rpm"
BASE_URL = "https://public.overte.org/build/overte/release/2026.04.1/"
ARTIFACTS = {
    CLIENT_NAME: "dc39f5b4694a1c48cfb1454a8922f6a25fa4db5820bf937113ebf4086aa99145",
    SERVER_NAME: "ecdabd358454b88dc669047fd1866b63114792280b331e48850a3c063464b2ae",
}
TABLET_ARTIFACTS = {
    'qml-module-qttest_5.15.3+dfsg-1_amd64.deb': 'b8f76e5d72bf4cf90501dceb0b00f2a5b474d314f85b1f1325514425860706c3',
    'libqt5quicktest5_5.15.3+dfsg-1_amd64.deb': 'a6437492130d09a9700503fb2b1aeb7b2be44e06cd25a358c74d6c5994163cea',
}
TABLET_BASE_URL = 'https://archive.ubuntu.com/ubuntu/pool/universe/q/qtdeclarative-opensource-src/'
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


def prepare(client_artifact=None, host_mode="fedora", **tool_options):
    if any(alive(entry["pid"]) for entry in load_state().values()):
        raise RuntimeError("The managed lab is running; preparation must not replace its tools or fixture files")
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
    if host_mode == "fedora" and (not (ROOT / "host-tools/usr/bin/Xvfb").exists() or not (ROOT / "host-tools/usr/bin/pulseaudio").exists()):
        if not Path("/etc/fedora-release").exists():
            raise RuntimeError("Fedora tool extraction is unavailable on this host; use prepare --host-tools system with the documented host paths")
        run(["dnf", "download", "--repo=fedora", "--repo=updates", "--destdir", ROOT / "rpms",
             "xorg-x11-server-Xvfb.x86_64", "pulseaudio.x86_64", "pulseaudio-libs.x86_64", "speexdsp.x86_64"])
    if host_mode == "fedora":
        for rpm in (ROOT / "rpms").glob("*.x86_64.rpm"):
            extract_rpm(rpm)
    prepare_tablet(host_mode, tool_options.get("slirp"))
    tools = select_tools(ROOT, host_mode, **tool_options)
    if host_mode == "system":
        # No success/skip fallback: a new host must prove actual ABI, private
        # audio modules and kernel isolation before it is allowed to start.
        result = preflight(ROOT, tools)
        (ROOT / "evidence/host-preflight.json").write_text(json.dumps(result, indent=2) + "\n")
    (ROOT / "config/host-tools.json").write_text(json.dumps(tools, indent=2) + "\n")
    (ROOT / "evidence/host-tools.json").write_text(json.dumps(tool_identities(tools), indent=2) + "\n")
    run([sys.executable, SOURCE / "create-assets.py"])
    for filename in ["native-participant.js", "textured-cube.gltf", "checker.png"]:
        shutil.copyfile(SOURCE / filename, ROOT / "http" / filename)
    (ROOT / "http/command.json").write_text('{"sequence":0}\n')
    artifacts = [{"filename":name,"url":BASE_URL+name,"sha256":digest} for name,digest in ARTIFACTS.items()]
    artifacts.extend({"filename":rpm.name,"sha256":hashlib.sha256(rpm.read_bytes()).hexdigest()}
                     for rpm in (ROOT / "rpms").glob("*.x86_64.rpm"))
    artifacts.extend({"filename":name,"url":TABLET_BASE_URL+name,"sha256":digest}
                     for name,digest in TABLET_ARTIFACTS.items())
    (ROOT / "evidence/artifacts.json").write_text(json.dumps(artifacts, indent=2) + "\n")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "sine=frequency=440:sample_rate=48000", "-t", "5", "-ac", "1", ROOT / "evidence/browser-microphone.wav"])
    print("Prepared pinned release binaries and original real-world assets.")


def prepare_tablet(host_mode="fedora", slirp=None):
    """Add matching Qt input modules and a user-space network helper only."""
    (ROOT / 'qt-tablet').mkdir(exist_ok=True)
    for name, expected in TABLET_ARTIFACTS.items():
        package = ROOT / 'downloads' / name
        if not package.exists():
            print(f'Downloading official matching Qt Tablet module {name}', flush=True)
            urllib.request.urlretrieve(TABLET_BASE_URL + name, package)
        if hashlib.sha256(package.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Tablet module differs from reviewed Qt 5.15.3 package: {name}')
        members = subprocess.check_output(['ar', 't', str(package)], text=True).splitlines()
        data = [member for member in members if member in ['data.tar.zst', 'data.tar.xz', 'data.tar.gz']]
        if len(data) != 1:
            raise RuntimeError('The pinned Tablet package lacks exactly one data archive')
        archive = ROOT / 'qt-tablet' / data[0]
        with archive.open('wb') as output:
            run(['ar', 'p', package, data[0]], stdout=output)
        run(['tar', '--extract', '--no-same-owner', '--file', archive, '--directory', ROOT / 'qt-tablet'])
        archive.unlink()
    if not slirp and not shutil.which('slirp4netns') and not (ROOT / 'host-tools/usr/bin/slirp4netns').exists():
        if host_mode != 'fedora' or not Path('/etc/fedora-release').exists():
            raise RuntimeError('Supply or install the documented slirp4netns host tool; no automatic platform fallback is permitted')
        run(['dnf', 'download', '--repo=fedora', '--repo=updates', '--destdir', ROOT / 'rpms', 'slirp4netns.x86_64'])
        packages = list((ROOT / 'rpms').glob('slirp4netns-*.x86_64.rpm'))
        if len(packages) != 1:
            raise RuntimeError('Expected exactly one official native network helper package')
        run(['rpm', '--checksig', packages[0]])
        extract_rpm(packages[0])
    for command in ['bwrap', 'xauth', 'ip', 'unshare', 'g++']:
        if not shutil.which(command):
            raise RuntimeError(f'The Tablet boundary requires the documented host tool: {command}')
    run([sys.executable, REPO / 'browser-client/tools/build-native-input.py',
         '--output', ROOT / 'native-input', '--qt-libraries', ROOT / 'appimage/squashfs-root/usr/lib'])


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def load_state():
    if STATE.is_symlink():
        raise RuntimeError("Managed lab state must not be a symbolic link")
    try:
        document = STATE.read_text()
    except FileNotFoundError:
        # An early preparation failure can leave the exact registry absent.
        # Do not catch malformed metadata, permissions or unrelated failures.
        return {}
    state = json.loads(document)
    if not isinstance(state, dict) or any(not isinstance(entry, dict)
            or type(entry.get("pid")) is not int or entry["pid"] <= 0
            or not isinstance(entry.get("startTicks"), str) or not entry["startTicks"].isdigit()
            for entry in state.values()):
        raise RuntimeError("Managed lab state must contain valid recorded process identities")
    return state


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
        if (ROOT / "config/host-tools.json").exists():
            raise RuntimeError("The selected laboratory runtime is missing; run prepare for its configured platform before start")
        prepare()
    tools = load_tools(ROOT)
    for port in [45100,45110] + ([8090] if gateway else []):
        probe = socket.socket()
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:
            probe.bind(("127.0.0.1",port))
        except OSError as error:
            raise RuntimeError(f"Port {port} is occupied; the lab will not replace another service") from error
        finally:
            probe.close()
    env = {**os.environ, "OVERTE_LAB_ROOT":str(ROOT), "QT_QPA_PLATFORM":"xcb", "QT_SCALE_FACTOR":"1", "QT_AUTO_SCREEN_SCALE_FACTOR":"0"}
    app = ROOT / "appimage/squashfs-root"
    server = ROOT / "server/opt/overte"
    server_env = {**env, "LD_LIBRARY_PATH":f"{server}/lib:{app}/usr/lib",
                  "QT_PLUGIN_PATH":str(app / "usr/plugins"),
                  "XDG_CONFIG_HOME":str(ROOT / "config"),"XDG_DATA_HOME":str(ROOT / "data"),
                  "HIFI_DOMAIN_SERVER_HTTP_PORT":"45100","HIFI_DOMAIN_SERVER_HTTPS_PORT":"45101",
                  "HIFI_DOMAIN_SERVER_PORT":"45102","HIFI_DOMAIN_SERVER_DTLS_PORT":"45103"}
    admin_credential = native_admin_credential()
    admin_password = admin_credential["token"]
    admin_file = ROOT / "runtime/admin.json"
    admin_file.write_text(json.dumps({"username":"browser-lab-admin","password":admin_password})+"\n")
    admin_file.chmod(0o600)
    admin_authorization = "Basic " + base64.b64encode(("browser-lab-admin:"+admin_password).encode()).decode()
    permissions = {key:True for key in PERMISSION_KEYS}
    config = {"version":2.7,"metaverse":{"local_port":45102,"automatic_networking":"disabled","enable_packet_verification":True},
              "security":{"http_username":"browser-lab-admin","http_password":admin_credential["nativeVerifier"],
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
        launch(name,[tools["xvfb"],f":{number}","-screen","0","1024x768x24","-nolisten","tcp"],env,state)
    for label in ["native","browser"]:
        script = ROOT / "runtime" / f"{label}.pa"
        script.write_text(f"load-module module-native-protocol-unix socket={ROOT}/runtime/{label}-pulse.sock auth-anonymous=1\n"
                          f"load-module module-null-sink sink_name={('lab' if label=='native' else 'browser')}_input rate=48000 channels=1\n"
                          f"load-module module-null-sink sink_name={('lab' if label=='native' else 'browser')}_output rate=48000 channels=2\n"
                          f"set-default-source {('lab' if label=='native' else 'browser')}_input.monitor\n"
                          f"set-default-sink {('lab' if label=='native' else 'browser')}_output\n")
        pulse_profile = ROOT / "runtime" / f"{label}-pulse-profile"
        pulse_profile.mkdir(mode=0o700, exist_ok=True)
        pulse_profile.chmod(0o700)
        pulse_env = {**env,"DBUS_SESSION_BUS_ADDRESS":"unix:path=/dev/null",
                     "XDG_RUNTIME_DIR":str(pulse_profile), "XDG_CONFIG_HOME":str(pulse_profile/"config"),
                     "XDG_DATA_HOME":str(pulse_profile/"data"), "XDG_CACHE_HOME":str(pulse_profile/"cache"),
                     "PULSE_RUNTIME_PATH":str(pulse_profile), "PULSE_STATE_PATH":str(pulse_profile/"state"),
                     "PULSE_COOKIE":str(pulse_profile/"cookie")}
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
    payload = {"security":{"standard_permissions":groups,"ip_permissions":[],"machine_fingerprint_permissions":[]},
               "authentication":{"enable_oauth2":False}}
    try:
        provisioning = post_guest_settings(payload, admin_authorization, server/"resources/describe-settings.json",
                                           ROOT/"config/domain.json", ROOT/"logs/domain.log")
    except ProvisioningDiagnosticError as error:
        print(json.dumps(error.diagnostic, sort_keys=True), file=sys.stderr, flush=True)
        raise
    print(json.dumps(provisioning, sort_keys=True), file=sys.stderr, flush=True)
    saved = json.loads((ROOT / "config/domain.json").read_text())["security"]["standard_permissions"]
    guest_readback = guest_permission_diagnostics(saved, guest)
    if not guest_readback['passed']:
        # Only fixed public group/flag enums and booleans; never settings content.
        print(json.dumps(guest_readback, sort_keys=True), file=sys.stderr, flush=True)
        raise RuntimeError("Saved domain guest permissions did not match the intended baseline")
    if provisioning['persistence']['outcome'] in ('parent-create-failed', 'open-failed', 'write-failed', 'commit-failed'):
        raise RuntimeError("Native settings provisioning reported a persistence failure")
    policy = {"version":1,"mode":"anonymous-baseline","domains":[{"domain":"overte://127.0.0.2:45102",
               "settingsFile":str(ROOT/"config/domain.json")} ]}
    (ROOT / "config/guest-policy.json").write_text(json.dumps(policy,indent=2)+"\n")
    print("Provisioned actual scene; saved and verified anonymous guest permissions.",flush=True)
    if gateway:
        start_gateway(state)
    print("Lab domain hifi://127.0.0.2:45102; native display :95; browser http://127.0.0.1:8090 (with --gateway)")


def start_gateway(state):
    tools = load_tools(ROOT)
    prepare_tablet(tools["mode"], tools["slirp"])
    native_root = ROOT / 'appimage/squashfs-root'
    qt_root = ROOT / 'qt-tablet/usr/lib/x86_64-linux-gnu'
    slirp = tools['slirp']
    gateway_env = {**os.environ,"OVERTE_LAB_ROOT":str(ROOT),"LD_LIBRARY_PATH":"","DISPLAY":":94","QT_QPA_PLATFORM":"xcb","QT_SCALE_FACTOR":"1","QT_AUTO_SCREEN_SCALE_FACTOR":"0",
                   "OVERTE_INTERFACE":str(ROOT/"appimage/squashfs-root/AppRun"),
                   "OVERTE_INTERFACE_LIBRARY_PATH":f'{native_root}/usr/lib:{qt_root}',
                   "QML2_IMPORT_PATH":f'{qt_root / "qt5/qml"}:{ROOT / "native-input/qml"}',
                   "OVERTE_GATEWAY_DEFAULT_SCRIPTS":str(native_root / 'usr/bin/scripts/defaultScripts.js'),
                   "OVERTE_GATEWAY_XVFB":tools["xvfb"],
                   "OVERTE_GATEWAY_SLIRP":slirp,
                   "OVERTE_GATEWAY_MANAGED_UDP_PORTS":"45102,45200,45201,45202,45203,45204,45205",
                   "OVERTE_GATEWAY_PUBLIC_PLACES":"overte_hub",
                   "OVERTE_GATEWAY_PUBLIC_INTERFACE":str(native_root / 'AppRun'),
                   "OVERTE_GATEWAY_PUBLIC_DEFAULT_SCRIPTS":str(native_root / 'usr/bin/scripts/defaultScripts.js'),
                   "OVERTE_GATEWAY_PUBLIC_INTERFACE_LIBRARY_PATH":f'{native_root}/usr/lib:{qt_root}',
                   "OVERTE_GATEWAY_PUBLIC_ASSET_ORIGINS":','.join([
                       'https://content.overte.org', 'https://content.zedwork.co.uk', 'https://files.thingvellir.net',
                       'https://raw.githubusercontent.com', 'https://overte.org', 'http://content.zedwork.co.uk',
                       'https://bas-skyspace.ams3.digitaloceanspaces.com', 'https://more.overte.org', 'https://github.com',
                       'https://upload.wikimedia.org', 'https://silverfish-freestuff.s3.eu-north-1.amazonaws.com']),
                   "OVERTE_GATEWAY_DOMAINS":"overte://127.0.0.2:45102",
                   "OVERTE_GATEWAY_NATIVE_SCHEME":"hifi",
                   "OVERTE_GATEWAY_PULSEAUDIO":tools["pulseaudio"],
                   "OVERTE_GATEWAY_PULSEAUDIO_MODULES":tools["pulseModules"],
                   "OVERTE_GATEWAY_PULSEAUDIO_LIBRARY_PATH":":".join(tools["pulseLibraries"]),
                   "OVERTE_GATEWAY_GUEST_POLICY":str(ROOT/"config/guest-policy.json"),
                   "OVERTE_GATEWAY_ASSET_ORIGINS":"https://content.overte.org,https://raw.githubusercontent.com,http://127.0.0.1:45110"}
    launch("gateway",["node",REPO/"browser-client/gateway/server.mjs"],gateway_env,state)
    wait_port(8090)


def stop(names=None):
    state=load_state()
    if not state:
        # No owned processes were recorded; never create state during cleanup.
        return
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
    parser.add_argument("action",choices=["prepare","start","stop","status","restart-gateway","preflight"])
    parser.add_argument("--client-artifact",type=Path)
    parser.add_argument("--host-tools", choices=["fedora", "system"], help="prepare: Fedora extraction (default) or verified system host tools")
    parser.add_argument("--xvfb", type=Path)
    parser.add_argument("--pulseaudio", type=Path)
    parser.add_argument("--pulse-modules", type=Path)
    parser.add_argument("--pulse-library-path", type=Path, action="append", default=[])
    parser.add_argument("--slirp", type=Path)
    parser.add_argument("--gateway",action="store_true")
    parser.add_argument("--open-browser",action="store_true",help="Open the local browser interface after a successful managed start")
    args=parser.parse_args()
    if args.action == "prepare" and args.host_tools != "system" and any([args.xvfb,args.pulseaudio,args.pulse_modules,args.pulse_library_path,args.slirp]):
        parser.error("Explicit host paths require --host-tools system")
    if args.action != "prepare" and any([args.host_tools,args.xvfb,args.pulseaudio,args.pulse_modules,args.pulse_library_path,args.slirp]):
        parser.error("Host tool selection belongs to prepare; subsequent commands use the verified saved configuration")
    if args.action=="prepare":prepare(args.client_artifact, args.host_tools or "fedora", xvfb=args.xvfb, pulseaudio=args.pulseaudio,
        pulse_modules=args.pulse_modules, pulse_libraries=args.pulse_library_path, slirp=args.slirp)
    elif args.action=="preflight":
        print(json.dumps(preflight(ROOT,load_tools(ROOT)),indent=2))
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
