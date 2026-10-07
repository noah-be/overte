#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Own the isolated direct-client domain and assignment processes only."""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
ROOT = REPO / "build/browser-direct/lab"
STATE = ROOT / "runtime/processes.json"
READINESS = ROOT / "runtime/assignment-readiness.json"
READINESS_STABLE_SECONDS = 3
PLAN = json.loads((SOURCE / "resources.json").read_text())
IMAGE = "ghcr.io/noah-be/overte/native-dependencies@sha256:a692b477cd2efdfc1f3d0f059a8eebba4852d37509a2efa945937ef2fe073373"
OWNER = hashlib.sha256(str(REPO).encode()).hexdigest()
CONTAINER_ROOT = "/src/build/browser-direct/lab"


def process_identity(pid: int) -> dict | None:
    try:
        root = Path("/proc") / str(pid)
        fields = (root / "stat").read_text().rsplit(") ", 1)[1].split()
        if fields[0] == "Z":
            return None
        return {"pid": pid, "startTicks": fields[19], "group": int(fields[2]),
                "executable": str((root / "exe").resolve()),
                "cwd": str((root / "cwd").resolve())}
    except (OSError, ValueError, IndexError):
        return None


def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def write_state(state: dict) -> None:
    temporary = STATE.with_suffix(".pending")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(STATE)


def owns_process(entry: dict) -> bool:
    actual = process_identity(entry["pid"])
    return actual is not None and all(actual[key] == entry[key]
                                      for key in ("pid", "startTicks", "group", "executable", "cwd"))


def container_owned(name: str) -> bool:
    result = subprocess.run(["podman", "inspect", "--format", "{{json .Config.Labels}}", name],
                            capture_output=True, text=True)
    if result.returncode:
        return False
    return json.loads(result.stdout).get("io.overte.browser-direct.owner") == OWNER


def check_ports(server_only: bool = False) -> None:
    tcp = (46100, 46101, 46104) if server_only else range(46100, 46121)
    udp = (46102, 46103, *range(46110, 46116), 46120) if server_only else range(46100, 46121)
    for kind, ports in ((socket.SOCK_STREAM, tcp),
                        (socket.SOCK_DGRAM, (*udp, *range(46130, 46230)))):
        for address in ("127.0.0.1", "127.0.0.3"):
            for port in ports:
                with socket.socket(socket.AF_INET, kind) as probe:
                    try:
                        if kind == socket.SOCK_STREAM:
                            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        probe.bind((address, port))
                        if kind == socket.SOCK_STREAM:
                            probe.listen(1)
                    except OSError as error:
                        raise RuntimeError(f"Port {port} is occupied; another owner's service will not be changed") from error


def check_software_displays() -> None:
    for number in PLAN["softwareDisplays"]:
        if Path(f"/tmp/.X{number}-lock").exists() or Path(f"/tmp/.X11-unix/X{number}").exists():
            raise RuntimeError(f"Display :{number} is occupied")


def graphics_status() -> dict:
    external = Path(PLAN["externalReadOnlyWorkspace"]) / "build/browser-lab/runtime/processes.json"
    active = []
    if external.exists():
        for name, entry in json.loads(external.read_text()).items():
            pid = entry.get("pid")
            if name in ("native", "gateway", "xvfb", "native-xvfb") and isinstance(pid, int):
                actual = process_identity(pid)
                if actual and actual["startTicks"] == str(entry.get("startTicks")):
                    active.append(name)
    return {"externalActiveKinds": active,
            "externalOwnersIdle": not active,
            "hardwareAllowed": False,
            "hardwareLeaseEstablished": False,
            "softwareAllowed": True,
            "softwareRequires": ["private displays 104/105", "llvmpipe/SwiftShader",
                                 "no /dev/dri or /dev/nvidia*", "private browser/native profiles"],
            "hardwareNote": "Idle inspection is insufficient to establish a lease; coordinate an exclusive window before hardware tests."}


def prepare() -> None:
    if any(owns_process(entry) for entry in read_state().values()):
        raise RuntimeError("Own lab is running; preparation must not overwrite live state")
    for name in ("config", "data", "cache", "logs", "runtime", "scene", "assets"):
        (ROOT / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    spec = importlib.util.spec_from_file_location("direct_scene", SOURCE / "prepare-scene.py")
    scene = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scene)
    manifest = scene.prepare()
    runtime_scene = "hub-subset.json.gz"
    if (ROOT / "scene/asset-provenance.json").is_file():
        scene.derive_atp_scene()
        manifest = scene.derive_https_scene()
        runtime_scene = "hub-with-atp-and-https.json.gz"
    token = secrets.token_hex(32)
    credentials = ROOT / "runtime/admin.json"
    credentials.write_text(json.dumps({"username": "direct-lab-admin", "password": token}) + "\n")
    credentials.chmod(0o600)
    permission_keys = ["id_can_connect", "id_can_rez_avatar_entities", "id_can_adjust_locks",
                       "id_can_rez", "id_can_rez_tmp", "id_can_write_to_asset_server",
                       "id_can_connect_past_max_capacity", "id_can_kick", "id_can_replace_content",
                       "id_can_get_and_set_private_user_data", "id_can_view_asset_urls"]
    guest = {key: key in ("id_can_connect", "id_can_rez_avatar_entities", "id_can_view_asset_urls")
             for key in permission_keys}
    config = {
        "version": 2.7, "metaverse": {"id": str(uuid.uuid4()), "local_port": 46102,
                                      "automatic_networking": "disabled", "enable_packet_verification": True},
        "security": {"http_username": "direct-lab-admin",
                     "http_password": hashlib.sha256(token.encode()).hexdigest(),
                     "ac_subnet_allowlist": ["127.0.0.3/32"],
                     "standard_permissions": [{"permissions_id": group, **guest}
                                              for group in ("anonymous", "localhost", "logged-in", "friends")],
                     "ip_permissions": [], "machine_fingerprint_permissions": []},
        "authentication": {"enable_oauth2": False}, "wizard": {"completed": True},
        "paths": {"/": {"viewpoint": "/155.084,-98.5,-397.328/0,0,0,1"}},
        "webrtc": {"enable_webrtc": True, "enable_webrtc_websocket_ssl": False,
                   "signaling_port": 46104, "signaling_address": "127.0.0.1"},
        "entity_server_settings": {"persistFilePath": f"{CONTAINER_ROOT}/scene/{runtime_scene}",
                                   "NoBackup": True, "persistFileDownload": False},
        "asset_server": {"enabled": True, "assets_path": f"{CONTAINER_ROOT}/assets"},
    }
    config_path = ROOT / "config/domain.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    config_path.chmod(0o600)
    print(json.dumps({"prepared": True, "sceneEntities": manifest["entityCount"],
                      "sceneSHA256": manifest["sceneSHA256"], "historicalHub": True}))


def launch(name: str, command: list[str], state: dict) -> None:
    container_name = f"overte-direct-{name}"
    if container_owned(container_name):
        raise RuntimeError(f"Owned container {name} already exists; inspect its state before starting")
    env = {
        "XDG_CONFIG_HOME": f"{CONTAINER_ROOT}/config", "XDG_DATA_HOME": f"{CONTAINER_ROOT}/data",
        "XDG_CACHE_HOME": f"{CONTAINER_ROOT}/cache", "QT_QPA_PLATFORM": "offscreen",
        "OVERTE_DOMAIN_SERVER_HTTP_ADDRESS": "127.0.0.3",
        "OVERTE_NODE_UDP_ADDRESS": "127.0.0.3",
        "HIFI_DOMAIN_SERVER_HTTP_PORT": "46100", "HIFI_DOMAIN_SERVER_HTTPS_PORT": "46101",
        "HIFI_DOMAIN_SERVER_PORT": "46102", "HIFI_DOMAIN_SERVER_DTLS_PORT": "46103",
        "OVERTE_DOMAIN_SERVER_WS_PORT": "46104",
        "OVERTE_BROWSER_ICE_BIND_ADDRESS": "127.0.0.3",
        "OVERTE_BROWSER_ICE_PORT_MIN": "46130", "OVERTE_BROWSER_ICE_PORT_MAX": "46229",
        "LD_LIBRARY_PATH": "/src/build/browser-direct/native/conanlibs/Release:/src/build/browser-direct/deps/prefix/lib",
    }
    arguments = ["podman", "run", "--rm", "--pull=never", "--network", "host", "--ipc", "private",
                 "--security-opt", "label=disable", "--name", container_name,
                 "--label", f"io.overte.browser-direct.owner={OWNER}",
                 "-v", f"{REPO}:/src", "-w", "/src"]
    pointer = json.loads((ROOT / "runtime/native-runtime.json").read_text())
    snapshot = Path(pointer["snapshot"]).resolve()
    if not snapshot.is_relative_to((ROOT / "runtime-snapshots").resolve()):
        raise RuntimeError("The selected native runtime is outside its owned snapshots")
    if hashlib.sha256((snapshot / "manifest.json").read_bytes()).hexdigest() != pointer["manifestSHA256"]:
        raise RuntimeError("The selected native runtime manifest changed")
    for source, target in ((snapshot / "native", "/src/build/browser-direct/native"),
                           (snapshot / "domain-resources", "/src/domain-server/resources"),
                           (snapshot / "datachannel-prefix", "/src/build/browser-direct/deps/prefix")):
        arguments.extend(("-v", f"{source}:{target}:ro"))
    for key, value in env.items():
        arguments.extend(("-e", f"{key}={value}"))
    arguments.extend((IMAGE, *command))
    with (ROOT / "logs" / f"{name}.log").open("w") as log:
        process = subprocess.Popen(arguments, cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    identity = process_identity(process.pid)
    if identity is None:
        raise RuntimeError(f"{name} exited before registration")
    state[name] = {**identity, "container": container_name, "owner": OWNER,
                   "runtimeSHA256": pointer["runtimeSHA256"]}
    write_state(state)
    time.sleep(0.2)
    if process.poll() is not None:
        raise RuntimeError(f"{name} exited; inspect its private lab log")


def wait_port(port: int, timeout: float = 20, address: str = "127.0.0.1") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((address, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Own lab port {port} did not start")


def wait_assignments(timeout: float = 30) -> list[str]:
    expected = {"audio-mixer", "avatar-mixer", "asset-server", "messages-mixer",
                "entity-script-server", "entity-server"}
    credentials = json.loads((ROOT / "runtime/admin.json").read_text())
    encoded = base64.b64encode(
        f"{credentials['username']}:{credentials['password']}".encode()).decode()
    deadline = time.monotonic() + timeout
    found = set()
    stable_since = None
    while time.monotonic() < deadline:
        for kind in ("domain", "assignments"):
            entry = read_state().get(kind)
            if entry is None or not owns_process(entry):
                raise RuntimeError(f"Owned {kind} process exited before readiness")
        connection = http.client.HTTPConnection("127.0.0.3", 46100, timeout=2)
        try:
            connection.request("GET", "/nodes.json", headers={"Authorization": f"Basic {encoded}"})
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError("Owned native readiness authentication failed")
            nodes = json.loads(response.read())["nodes"]
            if isinstance(nodes, dict):
                nodes = nodes.values()
            found = {node["type"] for node in nodes}
            if expected <= found:
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= READINESS_STABLE_SECONDS:
                    return sorted(expected)
            else:
                stable_since = None
        except (OSError, KeyError, ValueError, http.client.HTTPException):
            pass
        finally:
            connection.close()
        time.sleep(0.2)
    raise RuntimeError(f"Owned native assignment services did not register: {sorted(expected - found)}")


def start() -> None:
    state = read_state()
    if any(owns_process(entry) for entry in state.values()):
        raise RuntimeError("Own lab is already running")
    for target in ("domain-server", "assignment-client"):
        if not (REPO / "build/browser-direct/native" / target / target).is_file():
            raise RuntimeError(f"Build the own {target} target first")
    if not (ROOT / "config/domain.json").is_file():
        prepare()
    if not (ROOT / "runtime/native-runtime.json").is_file():
        subprocess.run([sys.executable, str(SOURCE / "snapshot-runtime.py")], check=True)
    check_ports(server_only=True)
    state = {}
    try:
        launch("domain", ["/src/build/browser-direct/native/domain-server/domain-server", "--user-config",
                          f"{CONTAINER_ROOT}/config/domain.json", "--logOptions", "nocolor,nojournald"], state)
        wait_port(46100, address="127.0.0.3")
        launch("assignments", ["/src/build/browser-direct/native/assignment-client/assignment-client",
                               "-a", "127.0.0.3", "--server-port", "46102",
                               "--disable-domain-port-auto-discovery", "--min-listen-port", "46110",
                               "-p", "46120", "-n", "6", "--min", "6", "--max", "6",
                               "--logOptions", "nocolor,nojournald"], state)
        wait_port(46104)
        assignment_types = wait_assignments()
        marker = {"schema": 1, "runtimeSHA256": state["domain"]["runtimeSHA256"],
                  "domainStartTicks": state["domain"]["startTicks"],
                  "domainPID": state["domain"]["pid"], "assignmentTypes": assignment_types,
                  "assignmentsStartTicks": state["assignments"]["startTicks"],
                  "assignmentsPID": state["assignments"]["pid"],
                  "stableSeconds": READINESS_STABLE_SECONDS,
                  "verifiedUnixTime": time.time(), "adminAuthenticated": True}
        temporary = READINESS.with_suffix(".pending")
        temporary.write_text(json.dumps(marker, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(READINESS)
        print(json.dumps({"started": True, "domain": PLAN["domain"],
                          "signaling": "ws://127.0.0.1:46104", "nativeParticipantsStarted": False,
                          "gpuDevicesMounted": False, "processKinds": list(state),
                          "assignmentTypes": assignment_types}))
    except BaseException:
        stop()
        raise


def stop() -> None:
    READINESS.unlink(missing_ok=True)
    state = read_state()
    for name, entry in reversed(list(state.items())):
        if entry.get("owner") != OWNER:
            raise RuntimeError("Process registry ownership differs; refusing cleanup")
        if container_owned(entry["container"]):
            subprocess.run(["podman", "stop", "--time", "10", entry["container"]],
                           check=True, stdout=subprocess.DEVNULL)
        if owns_process(entry):
            os.killpg(entry["group"], signal.SIGTERM)
            deadline = time.monotonic() + 5
            while owns_process(entry) and time.monotonic() < deadline:
                time.sleep(0.1)
            if owns_process(entry):
                os.killpg(entry["group"], signal.SIGKILL)
        state.pop(name)
        write_state(state)
    print(json.dumps({"stopped": True, "remainingOwnedProcesses": len(state)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "start", "stop", "status", "preflight", "graphics-status"))
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    (ROOT / "runtime").mkdir(exist_ok=True, mode=0o700)
    with (ROOT / "runtime/registry.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.operation == "prepare":
            prepare()
        elif args.operation == "start":
            start()
        elif args.operation == "stop":
            stop()
        elif args.operation == "preflight":
            check_ports()
            check_software_displays()
            print(json.dumps({"portsAvailable": True, "softwareDisplaysAvailable": True,
                              "graphics": graphics_status()}))
        elif args.operation == "graphics-status":
            print(json.dumps(graphics_status()))
        else:
            print(json.dumps({name: {"alive": owns_process(entry), "containerOwned": container_owned(entry["container"])}
                              for name, entry in read_state().items()}))


if __name__ == "__main__":
    main()
