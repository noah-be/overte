#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run real browsers on this worktree's software-only lab and own every process."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

REPO = Path(__file__).resolve().parents[2]
CLIENT = REPO / "browser-direct-client"
LAB = CLIENT / "lab"
sys.path.insert(0, str(LAB))
from manage import owns_process, process_identity  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_host_actions import NativeHostActions, read_native_observation  # noqa: E402

spec = importlib.util.spec_from_file_location("direct_software", LAB / "software-manage.py")
software = importlib.util.module_from_spec(spec)
spec.loader.exec_module(software)
STATE = REPO / "build/browser-direct"
REGISTRY = STATE / "lab/runtime/browser-tests.json"
DIRECT_NATIVE_MODES = ("asset-probe", "asset-dispatch-probe", "avatar-probe", "avatar-motion-probe",
                       "model-probe", "scene-probe", "direct", "benchmark", "benchmark-asset-route")
BROWSER_DRIVERS = {"benchmark": "benchmark.mjs", "benchmark-asset-route": "benchmark.mjs", "asset-probe": "asset-probe-driver.mjs",
    "asset-dispatch-probe": "asset-dispatch-probe-driver.mjs", "avatar-probe": "avatar-probe-driver.mjs",
    "avatar-motion-probe": "avatar-probe-driver.mjs", "model-probe": "model-probe-driver.mjs",
    "feature-probe": "feature-probe-driver.mjs", "input-probe": "input-probe-driver.mjs",
    "media-probe": "media-probe-driver.mjs", "permission-probe": "permission-probe-driver.mjs"}


def install_launcher_interruption_handlers():
    """Route TERM/HUP through the same bounded cleanup as normal exit.

    Detached drivers must not outlive a terminated host proof/action loop.
    A second signal cannot interrupt the existing identity-checked cleanup.
    """
    signals = (signal.SIGTERM, signal.SIGHUP)
    previous = {number: signal.getsignal(number) for number in signals}
    state = {"interrupted": False, "cleaning": False}

    def interrupted(number, _frame):
        if state["interrupted"] or state["cleaning"]:
            return
        state["interrupted"] = True
        raise SystemExit(128 + number)

    def begin_cleanup():
        state["cleaning"] = True

    def restore():
        for number, handler in previous.items():
            signal.signal(number, handler)

    for number in signals:
        signal.signal(number, interrupted)
    return begin_cleanup, restore


def require_validated_bundle(mode: str, digest: str | None, manifest: bytes | None = None) -> None:
    if mode != "asset-dispatch-probe":
        if digest is not None:
            raise RuntimeError("The reviewed bundle digest is specific to the page-baseline asset diagnostic")
        return
    if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise RuntimeError("Supply the reviewed complete production bundle-manifest SHA-256")
    if manifest is not None and hashlib.sha256(manifest).hexdigest() != digest:
        raise RuntimeError("The frozen production bundle differs from the explicitly reviewed artifact")


def driver_budget_seconds(mode: str, requested_timeout: int) -> int:
    if mode in ("benchmark", "benchmark-asset-route"):
        return 1200
    if mode == "permission-probe":
        return 180
    if mode == "asset-dispatch-probe":
        return 315  # One 285-second case plus at most30 seconds of natural cleanup.
    return min(1200, max(180, requested_timeout * 6))


def qualify_native_browser(mode: str, visitor: dict, qualification: dict, script_sha256: str, live=owns_process) -> str:
    if mode not in ("direct", "avatar-probe", "avatar-motion-probe"):
        raise RuntimeError("Only named native-participant tests use this binding")
    identity = visitor.get("parent")
    if not identity or qualification.get("nativeProcessIdentity") != identity or not live(identity):
        raise RuntimeError("Native qualification must bind the exact current registered live host process")
    if qualification.get("nativeMotionControlVersion") != 2 or qualification.get("observerScriptSHA256") != script_sha256:
        raise RuntimeError("Native qualification must bind the reviewed version-2 observer's exact frozen source")
    return qualification["explicitNativePlacementObservation"]["session"]


def require_native_action_mode(mode: str) -> None:
    if mode not in ("direct", "avatar-motion-probe"):
        raise RuntimeError("This browser mode never permits native movement")


def save(state: dict) -> None:
    temporary = REGISTRY.with_suffix(".pending")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(REGISTRY)


def refresh(state: dict) -> None:
    for entry in state.values():
        if owns_process(entry["parent"]):
            known = {child["pid"]: child for child in entry["children"] if owns_process(child)}
            known.update({child["pid"]: child for child in software.children(entry["parent"]["pid"])})
            entry["children"] = list(known.values())
        else:
            entry["children"] = [child for child in entry["children"] if owns_process(child)]
    save(state)


def stop(state: dict) -> None:
    refresh(state)
    targets = [identity for entry in reversed(list(state.values()))
               for identity in [*reversed(entry["children"]), entry["parent"]]]
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
        raise RuntimeError("An owned test process survived cleanup")
    save({})


def acquire_run_lock(lock, stop_requested: bool, registry: Path = REGISTRY) -> None:
    deadline = time.monotonic() + 10
    signalled = False
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if not stop_requested:
                raise
        # The active launcher owns this lock until its finally block cleans
        # descendants. Request its registered driver to exit, then acquire the
        # released lock; never race registry writes or signal guessed PIDs.
        if not signalled and registry.is_file():
            previous = json.loads(registry.read_text())
            target = previous.get("driver") or previous.get("http")
            if target and owns_process(target["parent"]):
                try:
                    os.kill(target["parent"]["pid"], signal.SIGTERM)
                    signalled = True
                except ProcessLookupError:
                    pass
        if time.monotonic() >= deadline:
            raise RuntimeError("The owned browser launcher did not release its lock after the stop request")
        time.sleep(0.1)


def start(state: dict, name: str, command: list[str], environment: dict, output: Path) -> subprocess.Popen:
    with output.open("w") as stream:
        process = subprocess.Popen(command, cwd=CLIENT, env=environment, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic() + 2
    identity = process_identity(process.pid)
    while identity is None and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
        identity = process_identity(process.pid)
    if identity is None:
        raise RuntimeError(f"Owned {name} did not start; inspect {output}")
    state[name] = {"parent": identity, "children": software.children(process.pid)}
    save(state)
    return process


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "feature-probe", "input-probe", "media-probe", "permission-probe", "asset-probe", "asset-dispatch-probe", "avatar-probe", "avatar-motion-probe", "model-probe", "scene-probe", "direct", "benchmark", "benchmark-asset-route"), default="smoke")
    parser.add_argument("--browsers", choices=("chromium",), default="chromium")
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--timeout", type=int, default=55, help="Browser join/renderer timeout in seconds")
    parser.add_argument("--expected-entities", type=int, help="Expected native scene count; defaults to this lab's prepared scene")
    parser.add_argument("--validated-bundle-sha256", help="Reviewed complete artifact manifest digest; required only by the page-baseline asset-dispatch diagnostic")
    parser.add_argument("--audio", action="store_true", help="Explicitly test synthetic Pulse audio against the actual native visitor")
    parser.add_argument("--stop", action="store_true", help="Stop only registered browser-test processes")
    args = parser.parse_args()
    if not args.run_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for character in args.run_id):
        parser.error("run-id must contain only letters, numbers, '.', '_' or '-'")
    allowed = {"chromium"}
    if not set(args.browsers.split(",")).issubset(allowed):
        parser.error("unknown browser")
    if not args.stop:
        require_validated_bundle(args.mode, args.validated_bundle_sha256)
    REGISTRY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with REGISTRY.with_suffix(".lock").open("a") as lock:
        acquire_run_lock(lock, args.stop)
        previous = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
        if args.stop:
            stop(previous)
            print(json.dumps({"remainingOwnedProcesses": 0}))
            return
        if any(owns_process(identity) for entry in previous.values()
               for identity in [entry["parent"], *entry["children"]]):
            raise RuntimeError("An owned browser test is already running")
        services = software.read_state()
        for name in ("xvfb-104", "browser-pulse"):
            if name not in services or not software.live(services[name]):
                raise RuntimeError("Start the owned software display and synthetic audio before browser tests")
        probe_entry = "avatar-probe" if args.mode == "avatar-motion-probe" else args.mode
        source_bundle = STATE / (probe_entry + "-bundle") if probe_entry in ("asset-probe", "avatar-probe", "permission-probe") else CLIENT / "dist"
        entry_path = "e2e/" + probe_entry + ".html" if probe_entry in ("asset-probe", "avatar-probe", "permission-probe") else "index.html"
        if not (source_bundle / entry_path).is_file():
            raise RuntimeError("Build the selected actual browser entry before testing")
        expected_entities = args.expected_entities
        native_peer = False
        readiness = None
        if args.mode in DIRECT_NATIVE_MODES:
            native_registry = STATE / "lab/runtime/processes.json"
            native_state = json.loads(native_registry.read_text()) if native_registry.exists() else {}
            if "domain" not in native_state or not owns_process(native_state["domain"]):
                raise RuntimeError("Start this worktree's own native domain before direct browser tests")
            readiness_path = STATE / "lab/runtime/assignment-readiness.json"
            if not readiness_path.is_file():
                raise RuntimeError("Wait for the lab to qualify all six actual assignment servers")
            readiness = json.loads(readiness_path.read_text())
            runtime = json.loads((STATE / "lab/runtime/native-runtime.json").read_text())
            required_types = {"audio-mixer", "avatar-mixer", "asset-server", "messages-mixer",
                              "entity-server", "entity-script-server"}
            if readiness.get("runtimeSHA256") != runtime.get("runtimeSHA256") or (
                readiness.get("domainStartTicks") != native_state["domain"]["startTicks"]
                or readiness.get("domainPID") != native_state["domain"]["pid"]
                or not required_types.issubset(set(readiness.get("assignmentTypes", [])))
                or readiness.get("adminAuthenticated") is not True):
                raise RuntimeError("Native assignment readiness does not identify the current owned runtime and domain")
            if "assignments" not in native_state or not owns_process(native_state["assignments"]) or (
                readiness.get("assignmentsPID") != native_state["assignments"]["pid"]
                or readiness.get("assignmentsStartTicks") != native_state["assignments"]["startTicks"]
                or readiness.get("stableSeconds", 0) < 3):
                raise RuntimeError("Native assignment readiness does not identify the current owned assignment client")
            if expected_entities is None:
                scene_path = STATE / "lab/scene/hub-subset.json"
                expected_entities = len(json.loads(scene_path.read_text())["Entities"])
            visitor_registry = STATE / "lab/runtime/native-visitor.json"
            visitor = json.loads(visitor_registry.read_text()) if visitor_registry.exists() else {}
            native_peer = bool(visitor) and visitor.get("release") == "2026.04.1" and (
                owns_process(visitor["parent"]) or any(owns_process(child) for child in visitor["children"]))
        if args.mode in ("avatar-probe", "avatar-motion-probe", "benchmark-asset-route") and not native_peer:
            raise RuntimeError("This participant-bound diagnostic requires the qualified actual native visitor")
        if args.audio and (args.mode != "direct" or not native_peer):
            raise RuntimeError("Synthetic audio interoperability requires direct mode and the owned pinned native visitor")
        # Refuse an occupied port rather than connecting to a foreign server.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 46106))
        with socket.socket() as negative_probe:
            negative_probe.bind(("127.0.0.1", 46118))
        result = STATE / "e2e" / args.run_id
        result.mkdir(parents=True, exist_ok=False, mode=0o700)
        if readiness:
            readiness_copy = result / "native-readiness.json"
            readiness_copy.write_text(json.dumps(readiness, indent=2) + "\n")
            readiness_copy.chmod(0o600)
        # Freeze a production artifact for the entire browser matrix. A parallel
        # source build must not remove the JavaScript hash a browser just loaded.
        bundle = result / "bundle"
        shutil.copytree(source_bundle, bundle)
        manifest = [{"path": str(path.relative_to(bundle)), "bytes": path.stat().st_size,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in sorted(bundle.rglob("*")) if path.is_file()]
        for entry in manifest:
            source = source_bundle / entry["path"]
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError("The production bundle changed while taking its test snapshot; retry after the build")
        manifest_path = result / "bundle-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        manifest_path.chmod(0o600)
        require_validated_bundle(args.mode, args.validated_bundle_sha256, manifest_path.read_bytes())
        environment = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(STATE / "browsers"),
                       "PULSE_SERVER": f"unix:{STATE}/lab/runtime/b.sock",
                       "PULSE_SOURCE": "browser_microphone", "PULSE_SINK": "browser_output"}
        state: dict = {}
        host_actions = None
        begin_cleanup, restore_interruption_handlers = install_launcher_interruption_handlers()
        try:
            if args.mode in ("direct", "avatar-probe", "avatar-motion-probe") and native_peer:
                qualification = json.loads((STATE / "lab/runtime/native-visitor-qualification.json").read_text())
                session = qualify_native_browser(args.mode, visitor, qualification,
                    hashlib.sha256((LAB / "native-visitor.js").read_bytes()).hexdigest())
                def launch_native_action(name, operation, output):
                    require_native_action_mode(args.mode)
                    # Only fixed operations chosen by NativeHostActions reach this
                    # host command. The page/app never supplies executable, PID,
                    # path, argument, environment or native endpoint selectors.
                    return start(state, name, [sys.executable, str(LAB / "native-visitor.py"), operation],
                                 os.environ.copy(), output)

                def cancel_native_action(name):
                    entry = state.get(name)
                    if entry:
                        for identity in [*reversed(entry["children"]), entry["parent"]]:
                            if owns_process(identity):
                                try:
                                    os.kill(identity["pid"], signal.SIGTERM)
                                except ProcessLookupError:
                                    pass

                host_actions = NativeHostActions(result / "native-host-actions", visitor["parent"], session,
                    lambda: json.loads(visitor_registry.read_text()),
                    lambda: read_native_observation(STATE / "lab/logs/native-visitor.log"),
                    owns_process, launch_native_action, cancel_native_action)
                host_actions.proof(True)
            server = start(state, "http", ["node", str(CLIENT / "node_modules/vite/bin/vite.js"),
                                           "preview", "--host", "127.0.0.1", "--port", "46106", "--strictPort",
                                           "--outDir", str(bundle)],
                           environment, result / "http.log")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Owned production server exited")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:46106/{entry_path}", timeout=0.5) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Owned production server did not become ready")
            script = BROWSER_DRIVERS.get(args.mode, "driver.mjs")
            command = [sys.executable, str(LAB / "software-run.py"), "--display", "104", "--", "node",
                       str(CLIENT / "e2e" / script),
                       "--mode", args.mode, "--browsers", args.browsers,
                       "--result", str(result), "--timeout", str(args.timeout),
                       "--expected-entities", str(expected_entities or 83),
                       "--native-peer", str(native_peer).lower(), "--synthetic-audio", str(args.audio).lower()]
            if args.validated_bundle_sha256:
                command += ["--validated-bundle-sha256", args.validated_bundle_sha256]
            driver = start(state, "driver", command, environment, result / "driver.log")
            # A four-profile software comparison must remain below 20 minutes;
            # individual waits cannot multiply into an unbounded batch budget.
            overall_seconds = driver_budget_seconds(args.mode, args.timeout)
            deadline = time.monotonic() + overall_seconds
            while driver.poll() is None:
                refresh(state)
                if host_actions:
                    if args.mode == "avatar-probe":
                        host_actions.proof()  # Read-only PID/session qualification; no action requests accepted.
                    else:
                        host_actions.tick()
                if time.monotonic() > deadline:
                    raise RuntimeError("Browser driver exceeded its bounded run deadline")
                time.sleep(0.25)
            refresh(state)
            evidence = result / "results.json"
            if evidence.is_file():
                report = json.loads(evidence.read_text())
                print(json.dumps({"result": str(evidence), "passed": report["passed"],
                                  "browsers": [{"browser": browser["browser"], "version": browser.get("version"),
                                                "passed": browser["passed"]} for browser in report["browsers"]]}))
            else:
                print(json.dumps({"result": str(result), "passed": False, "driverLog": str(result / "driver.log")}))
            raise SystemExit(driver.returncode)
        finally:
            begin_cleanup()
            try:
                if host_actions:
                    host_actions.close()
            finally:
                try:
                    stop(state)
                finally:
                    restore_interruption_handlers()


if __name__ == "__main__":
    main()
