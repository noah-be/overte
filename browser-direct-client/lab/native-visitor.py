#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Own one isolated packaged native visitor for actual browser/native tests."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from manage import REPO, ROOT, SOURCE, owns_process, process_identity

spec = importlib.util.spec_from_file_location("software_management", SOURCE / "software-manage.py")
software = importlib.util.module_from_spec(spec)
spec.loader.exec_module(software)
STATE = ROOT / "runtime/native-visitor.json"
LOG = ROOT / "logs/native-visitor.log"
PLACEMENT = ROOT / "runtime/native-placement.json"
PLACEMENT_HTTP = ROOT / "https-assets/native-control/placement.json"
MOTION = ROOT / "runtime/native-motion.json"
MOTION_HTTP = ROOT / "https-assets/native-control/motion.json"


def write_control(value: dict, targets: tuple[Path, ...]) -> None:
    for target in targets:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = target.with_suffix(".pending")
        temporary.write_text(json.dumps(value, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(target)


def write_placement(value: dict) -> None:
    write_control(value, (PLACEMENT, PLACEMENT_HTTP))


def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def write_state(state: dict) -> None:
    temporary = STATE.with_suffix(".pending")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(STATE)


def alive(state: dict) -> bool:
    return bool(state) and (owns_process(state["parent"]) or
                            any(owns_process(child) for child in state["children"]))


def evidence() -> dict | None:
    if not LOG.exists():
        return None
    with LOG.open("rb") as stream:
        stream.seek(max(0, LOG.stat().st_size - 262144))
        lines = stream.read().decode("utf-8", "replace").splitlines()
    marker = "DIRECT_LAB_NATIVE "
    for line in reversed(lines):
        if marker in line:
            try:
                return json.loads(line.split(marker, 1)[1])
            except json.JSONDecodeError:
                continue
    return None


def private_ca_bundle() -> tuple[Path, dict]:
    certificate = ROOT / "runtime/fixture-tls/cert.pem"
    if not certificate.is_file():
        raise RuntimeError("Start this lab's own HTTPS fixture before the native visitor")
    system_bundle = next((path for path in (Path("/etc/pki/tls/certs/ca-bundle.crt"),
                                           Path("/etc/ssl/certs/ca-certificates.crt"))
                          if path.is_file()), None)
    if system_bundle is None:
        raise RuntimeError("No existing system CA bundle is available for process-local native trust")
    fixture = certificate.read_bytes()
    bundle = ROOT / "runtime/native-fixture-ca.pem"
    bundle.write_bytes(system_bundle.read_bytes().rstrip() + b"\n" + fixture)
    bundle.chmod(0o600)
    return bundle, {"processLocal": True, "verificationDisabled": False,
                    "fixtureCertificateSHA256": hashlib.sha256(fixture).hexdigest(),
                    "bundleSHA256": hashlib.sha256(bundle.read_bytes()).hexdigest()}


def private_hosts_file() -> tuple[Path, dict]:
    source = Path("/etc/hosts").read_text()
    names = {"stun1.l.google.com"}
    preserved = []
    for line in source.splitlines():
        body, separator, comment = line.partition("#")
        words = body.split()
        if words and any(name in names for name in words[1:]):
            remaining = [name for name in words[1:] if name not in names]
            if remaining:
                preserved.append(" ".join([words[0], *remaining]) +
                                 (" #" + comment if separator else ""))
        else:
            preserved.append(line)
    owned = ROOT / "runtime/native-hosts"
    owned.write_text("127.0.0.1 stun1.l.google.com\n" + "\n".join(preserved) + "\n")
    owned.chmod(0o600)
    return owned, {"processLocal": True, "hostname": "stun1.l.google.com",
                   "mappedAddress": "127.0.0.1", "standardSTUNFallbackRequired": True,
                   "hostsSHA256": hashlib.sha256(owned.read_bytes()).hexdigest()}


def start() -> None:
    state = read_state()
    if alive(state):
        raise RuntimeError("The owned native visitor is already running")
    software_state = software.read_state()
    for name in ("xvfb-105", "native-pulse"):
        if name not in software_state or not software.live(software_state[name]):
            raise RuntimeError("Start the owned software display and synthetic audio first")
    domain_state = json.loads((ROOT / "runtime/processes.json").read_text())
    readiness_path = ROOT / "runtime/assignment-readiness.json"
    if not readiness_path.is_file():
        raise RuntimeError("Qualify this worktree's own domain and all six assignments first")
    readiness = json.loads(readiness_path.read_text())
    for kind, pid_field, ticks_field in (("domain", "domainPID", "domainStartTicks"),
                                       ("assignments", "assignmentsPID", "assignmentsStartTicks")):
        entry = domain_state.get(kind)
        if not entry or not owns_process(entry) or entry["pid"] != readiness[pid_field] or \
                entry["startTicks"] != readiness[ticks_field] or \
                entry["runtimeSHA256"] != readiness["runtimeSHA256"]:
            raise RuntimeError("Current native runtime differs from the stable assignment readiness marker")
    executable = ROOT / "native-release/squashfs-root/AppRun"
    if not executable.is_file():
        raise RuntimeError("Prepare the checksum-pinned native release first")
    cache = ROOT / "native-visitor-cache"
    cache.mkdir(mode=0o700, exist_ok=True)
    ca_bundle, trust = private_ca_bundle()
    hosts_file, network_setup = private_hosts_file()
    write_placement({"enabled": False})
    write_control({"enabled": False}, (MOTION_HTTP,))
    environment = {**os.environ, "PULSE_SERVER": f"unix:{ROOT}/runtime/n.sock",
                   "PULSE_SOURCE": "native_input.monitor", "PULSE_SINK": "native_output",
                   "SSL_CERT_FILE": str(ca_bundle), "CURL_CA_BUNDLE": str(ca_bundle),
                   "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --use-angle=swiftshader --no-sandbox"}
    command = [sys.executable, str(SOURCE / "software-run.py"), "--display", "105",
               "--hosts-file", str(hosts_file), "--ca-bundle", str(ca_bundle), "--",
               str(executable), "--allowMultipleInstances", "--url", "hifi://127.0.0.3:46102",
               "--listenPort", "46116", "--cache", str(cache), "--no-updater",
               "--no-login-suggestion", "--suppress-settings-reset", "--defaultScriptsOverride",
               (SOURCE / "native-visitor.js").as_uri(),
               "--disableDisplayPlugins", "OpenXR,OpenVR,OpenVR (Vive)",
               "--disableInputPlugins", "OpenXR,OpenVR,OpenVR (Vive),SDL2",
               "--displayName", "direct-lab-native", "--concurrent-downloads", "4"]
    with LOG.open("w") as output:
        process = subprocess.Popen(command, cwd=REPO, env=environment, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(0.5)
    identity = process_identity(process.pid)
    if identity is None or process.poll() is not None:
        raise RuntimeError("Owned native visitor exited; inspect its private log")
    state = {"parent": identity, "children": software.children(process.pid), "display": 105,
             "release": "2026.04.1", "syntheticAudioOnly": True, "httpsTrust": trust,
             "restrictedNetworkSetup": network_setup,
             "observerScriptSHA256": hashlib.sha256((SOURCE / "native-visitor.js").read_bytes()).hexdigest()}
    write_state(state)
    print(json.dumps({"started": True, "display": 105, "release": state["release"],
                      "syntheticAudioOnly": True, "gpuDevicesMounted": False}))


def place_ahead() -> None:
    observed = evidence()
    if not alive(read_state()) or not observed or not observed["connected"]:
        raise RuntimeError("The owned native visitor must first join normally")
    position = observed["position"]
    center = {"x": 155.084, "y": -98.5, "z": -397.328}
    if sum((position[axis] - center[axis]) ** 2 for axis in center) > 4:
        raise RuntimeError("Confirm the actual ordinary Hub spawn before native test placement")
    request = {"enabled": True, "requestId": str(uuid.uuid4()), "session": observed["session"],
               "label": "Explicit native participant test setup after independently observed domain spawn",
               "normalDomainSpawnObserved": observed, "offset": {"x": 0, "y": 0, "z": -3}}
    write_placement(request)
    print(json.dumps({"placementRequested": True, "participant": "owned native visitor",
                      "browserMoved": False, "normalPosition": position, "offset": request["offset"]}))


def retry_path() -> None:
    observed = evidence()
    if not alive(read_state()) or not observed or not observed["connected"] or observed.get("nativeTestSetup"):
        raise RuntimeError("Retry the ordinary domain path only on the joined native visitor before test placement")
    if observed.get("nativeNavigationRetry"):
        raise RuntimeError("The owned native visitor already performed its bounded ordinary path retry")
    request = {"enabled": True, "requestId": str(uuid.uuid4()), "session": observed["session"],
               "operation": "ordinary-domain-path", "url": "hifi://127.0.0.3:46102/",
               "label": "Explicit native ordinary '/' navigation retry after packaged-client startup",
               "beforeNavigationObserved": observed}
    write_placement(request)
    print(json.dumps({"ordinaryPathRetryRequested": True, "participant": "owned native visitor",
                      "nativePathLookupRequired": True, "browserMoved": False,
                      "beforePosition": observed["position"]}))


def motion_context() -> tuple[dict, dict]:
    state = read_state()
    observed = evidence()
    marker = json.loads((ROOT / "runtime/assignment-readiness.json").read_text())
    qualified = json.loads((ROOT / "runtime/native-visitor-qualification.json").read_text())
    if not state or not owns_process(state["parent"]) or not observed or \
            not observed.get("connected") or observed.get("domain") != "127.0.0.3" or \
            qualified["nativeProcessIdentity"] != state["parent"] or \
            qualified["runtimeSHA256"] != marker["runtimeSHA256"] or \
            qualified["explicitNativePlacementObservation"]["session"] != observed.get("session") or \
            not qualified.get("worldLoadingQualified") or \
            not qualified.get("modelGraphicsAndNativeQtHTTPSQualified"):
        raise RuntimeError("Motion requires the current independently qualified native visitor")
    services = json.loads((ROOT / "runtime/processes.json").read_text())
    for kind, prefix in (("domain", "domain"), ("assignments", "assignments")):
        entry = services.get(kind)
        if not entry or not owns_process(entry) or entry["pid"] != marker[prefix + "PID"] or \
                entry["startTicks"] != marker[prefix + "StartTicks"] or \
                entry["runtimeSHA256"] != marker["runtimeSHA256"]:
            raise RuntimeError("Qualified native services changed before the motion step")
    setup = observed.get("nativeTestSetup")
    if observed.get("nativeMotionControlVersion") != 2 or not setup or \
            setup.get("session") != observed["session"] or \
            setup.get("requestId") != qualified["explicitNativePlacementObservation"]["nativeTestSetup"]["requestId"] or \
            not 0 <= time.time() - observed.get("observedAtUnixTime", 0) <= 6:
        raise RuntimeError("Require the current fresh native motion observer after explicit initial placement")
    return state, observed


def save_motion_record(record: dict) -> None:
    trial = ROOT / "runtime/native-motion-history" / str(uuid.UUID(record["requestId"])) / "evidence.json"
    write_control(record, (MOTION, trial))


def await_motion(record: dict, phase: str, reference: dict) -> dict:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        state, observed = motion_context()
        if state["parent"] != record["nativeProcessIdentity"] or observed["session"] != record["session"]:
            raise RuntimeError("Native process or session changed during the motion step")
        motion = observed.get("nativeMotionTest")
        if motion and motion.get("requestId") == record["requestId"] and motion.get("phase") == phase and \
                observed["sequence"] > reference["sequence"]:
            target = motion["moveTargetPosition" if phase == "moved" else "beforePosition"]
            if any(abs(observed["position"][axis] - target[axis]) > 0.25 for axis in ("x", "z")):
                raise RuntimeError("Actual native horizontal pose did not confirm the bounded motion")
            return observed
        time.sleep(0.1)
    raise RuntimeError("The bounded native motion request did not produce a newer confirmed observation")


def motion(operation: str) -> None:
    state, observed = motion_context()
    previous = json.loads(MOTION.read_text()) if MOTION.exists() else {}
    if operation == "move":
        if observed.get("nativeMotionTest") or previous.get("session") == observed["session"]:
            raise RuntimeError("Only one native motion trial is allowed in this process/session")
        record = {"requestId": str(uuid.uuid4()), "session": observed["session"],
                  "runtimeSHA256": json.loads((ROOT / "runtime/assignment-readiness.json").read_text())["runtimeSHA256"],
                  "nativeProcessIdentity": state["parent"], "beforeMoveObservation": observed,
                  "browserMoved": False, "label": "Explicit native-only participant motion after ordinary spawn and rig proof"}
    else:
        record = previous
        status = observed.get("nativeMotionTest")
        if record.get("session") != observed["session"] or record.get("nativeProcessIdentity") != state["parent"] or \
                not status or status.get("requestId") != record.get("requestId") or \
                status.get("phase") != "moved" or record.get("restoreRequested"):
            raise RuntimeError("Restore only the current once-moved native participant trial")
        record["restoreRequested"] = True
        record["beforeRestoreObservation"] = observed
    issued = time.time()
    instruction = {"enabled": True, "operation": operation, "requestId": record["requestId"],
                   "commandId": str(uuid.uuid4()), "session": observed["session"],
                   "placementRequestId": observed["nativeTestSetup"]["requestId"],
                   "referenceSequence": observed["sequence"], "issuedUnixTime": issued,
                   "expiresUnixTime": issued + 6, "beforePosition": observed["position"],
                   "offset": {"x": 0, "y": 0, "z": -1}}
    record[operation + "Instruction"] = instruction
    save_motion_record(record)
    write_control(instruction, (MOTION_HTTP,))
    try:
        actual = await_motion(record, "moved" if operation == "move" else "restored", observed)
        record[operation + "Observation"] = actual
    finally:
        write_control({"enabled": False}, (MOTION_HTTP,))
        record[operation + "InstructionDisabledUnixTime"] = time.time()
        save_motion_record(record)
    print(json.dumps({"operation": operation, "requestId": record["requestId"],
                      "participant": "owned native visitor", "browserMoved": False,
                      "session": actual["session"], "nativeSequenceBefore": observed["sequence"],
                      "nativeSequenceAfter": actual["sequence"], "positionBefore": observed["position"],
                      "positionAfter": actual["position"], "nativeMotionTest": actual["nativeMotionTest"]}))


def stop() -> None:
    state = read_state()
    if state:
        if owns_process(state["parent"]):
            state["children"] = software.children(state["parent"]["pid"])
        targets = [*reversed(state["children"]), state["parent"]]
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
                try:
                    os.kill(identity["pid"], signal.SIGKILL)
                except ProcessLookupError:
                    pass
        time.sleep(0.2)
        if any(owns_process(identity) for identity in targets):
            raise RuntimeError("Owned native visitor failed cleanup")
    write_state({})
    print(json.dumps({"stopped": True, "remainingOwnedProcesses": 0}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("start", "status", "stop", "place-ahead", "retry-path",
                                              "motion-move", "motion-restore"))
    args = parser.parse_args()
    (ROOT / "runtime").mkdir(parents=True, mode=0o700, exist_ok=True)
    with (ROOT / "runtime/native-visitor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.operation == "start":
            start()
        elif args.operation == "stop":
            stop()
        elif args.operation == "place-ahead":
            place_ahead()
        elif args.operation == "retry-path":
            retry_path()
        elif args.operation.startswith("motion-"):
            motion(args.operation.removeprefix("motion-"))
        else:
            state = read_state()
            if state and owns_process(state["parent"]):
                state["children"] = software.children(state["parent"]["pid"])
                write_state(state)
            print(json.dumps({"alive": alive(state), "display": 105, "evidence": evidence()}))


if __name__ == "__main__":
    main()
