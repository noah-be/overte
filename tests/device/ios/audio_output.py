#!/usr/bin/env python3
"""Verify physical output PCM and voice mute with system volume zero."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
from threading import Thread
import time
import wave

DEVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE_ROOT))
from adapters.appium.adapter import WebDriver, WebDriverRequestError  # noqa: E402
from adapters.native_binding import PrivateParser  # noqa: E402
from adapters.voice_transport import appium_read  # noqa: E402
from voice_contract import wav  # noqa: E402
from voice_peer.voice_signal import analyze, write_wav  # noqa: E402
from ios.acoustic_loopback import AcousticError, handle_permission, wait_capture_removal  # noqa: E402


class AudioOutputError(AcousticError):
    """Closed diagnostics for the internal physical-device output check."""


def validate_native(status: dict, permission: int, muted: bool, *, zero: bool) -> None:
    active_input = permission == 1 and not muted
    expected_outcome = 3 if muted else (2 if permission == 1 else 1)
    if (status.get("iosPermission") != permission or status.get("iosOutcome") != expected_outcome
            or status.get("nativeMuted") is not muted or status.get("iosCaptureAllowed") is not active_input
            or status.get("inputPresent") is not active_input
            or any(status.get(key) is not True for key in ("physicalDevice", "builtInSpeaker", "iosForeground"))
            or any(status.get(key) is not False for key in (
                "sourceEnabled", "sourceClockActive", "iosInterrupted", "prepared", "measurementMode"))
            or (zero and (type(status.get("outputVolume")) not in (int, float) or status["outputVolume"] != 0))
            or (active_input and (status.get("inputState") != 0 or status.get("inputError") != 0))):
        raise AudioOutputError("AUDIO_OUTPUT_NATIVE_STATE_INVALID")


def evaluate(document: dict, run: dict, private: Path) -> dict:
    if (not isinstance(document, dict) or document.get("runId") != run["id"]
            or document.get("schemaVersion") != 1 or document.get("ok") is not True
            or document.get("error") or document.get("cleanup", {}).get("restored") is not True
            or document.get("foregroundContinuous") is not True):
        raise AudioOutputError("AUDIO_OUTPUT_RUN_OR_CLEANUP_FAILED")
    transitions = document.get("voiceTransitions")
    if not isinstance(transitions, list) or len(transitions) != 3:
        raise AudioOutputError("AUDIO_OUTPUT_VOICE_TRANSITIONS_MISSING")
    for index, phase in enumerate(("unmuted", "muted", "unmuted-again")):
        if not isinstance(transitions[index], dict) or transitions[index].get("phase") != phase:
            raise AudioOutputError("AUDIO_OUTPUT_VOICE_TRANSITION_INVALID")
        validate_native(transitions[index].get("status", {}), run["permission"], index == 1, zero=False)
    captures = document.get("captures")
    if not isinstance(captures, list) or len(captures) != 4:
        raise AudioOutputError("AUDIO_OUTPUT_CAPTURES_MISSING")
    measurements = []
    phases = ("quiet-control", "local-playback-1", "local-playback-2", "local-playback-3")
    for index, (capture, phase) in enumerate(zip(captures, phases)):
        if not isinstance(capture, dict) or capture.get("ok") is not True or capture.get("phase") != phase:
            raise AudioOutputError("AUDIO_OUTPUT_CAPTURE_INVALID")
        status = capture.get("status", {})
        validate_native(status, run["permission"], True, zero=True)
        challenge = run["challenges"][max(0, index - 1)]
        if capture.get("challenge") != challenge:
            raise AudioOutputError("AUDIO_OUTPUT_NONCE_MISMATCH")
        path = private / f"{index}.wav"
        path.write_bytes(wav(capture))
        with wave.open(str(path), "rb") as source:
            if not 7.5 <= source.getnframes() / source.getframerate() <= 8.5:
                raise AudioOutputError("AUDIO_OUTPUT_CAPTURE_TRUNCATED")
        measured = analyze(path, challenge, "absent" if index == 0 else "present")
        if (not measured["passed"] or (index == 0 and any(
                analyze(path, nonce, "absent")["patternDetected"] for nonce in run["challenges"]))):
            raise AudioOutputError("AUDIO_OUTPUT_CHALLENGE_MISMATCH")
        measured.update(phase=phase, captureSha256=capture["sha256"], status=status)
        measurements.append(measured)
    return {"passed": True, "voiceTransitions": transitions, "measurements": measurements, "cleanup": document["cleanup"],
            "observedBuildVersion": document.get("buildVersion"),
            "startedEpochMs": document.get("startedEpochMs"), "completedEpochMs": document.get("completedEpochMs")}

@contextmanager
def serve_script(address: str, run: dict):
    routes = {}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = routes.get(self.path)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript" if self.path.endswith(".js") else "audio/wav")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer((address, 0), Handler)
    base = f"http://{address}:{server.server_port}"
    try:
        with tempfile.TemporaryDirectory(prefix="overte-output-challenges-") as private:
            run["urls"] = []
            for index, challenge in enumerate(run["challenges"]):
                path = Path(private) / f"{index}.wav"
                write_wav(path, challenge)
                route = f"/{run['id']}-{index}.wav"
                routes[route] = path.read_bytes()
                run["urls"].append(base + route)
        route = f"/{run['id']}.js"
        routes[route] = ("var OVERTE_OUTPUT_RUN = " + json.dumps(run) + ";\n").encode() + Path(__file__).with_suffix(".js").read_bytes()
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield base + route
        finally:
            server.shutdown()
            thread.join(timeout=5)
    finally:
        server.server_close()


def parser():
    value = PrivateParser(description=__doc__, allow_abbrev=False)
    value.add_argument("--target-config", type=Path, required=True, help="private config with exactly one enabled iOS target")
    value.add_argument("--listen-address", required=True, help="test PC IPv4 address reachable from the iPad")
    value.add_argument("--output", type=Path, required=True, help="new private evidence directory")
    value.add_argument("--source-revision", required=True)
    value.add_argument("--producer-artifact-sha256", required=True)
    value.add_argument("--expected-build-version", required=True, help="exact About.buildVersion of the installed candidate")
    value.add_argument("--microphone-decision", choices=("allow", "deny"), default="allow")
    value.add_argument("--reset-microphone", action="store_true", help="exercise the first request; explicitly answer its dialog before launching the test")
    value.add_argument("--lock-file", action="append", type=Path, help="additional exclusive device-lab lock; repeat when required")
    return value


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    os.umask(0o077)
    if (not re.fullmatch(r"[0-9a-f]{40}", args.source_revision)
            or not re.fullmatch(r"[0-9a-f]{64}", args.producer_artifact_sha256)
            or not args.expected_build_version):
        raise AudioOutputError("AUDIO_OUTPUT_CANDIDATE_IDENTITY_INVALID")
    address = ipaddress.IPv4Address(args.listen_address)
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise AudioOutputError("AUDIO_OUTPUT_LISTEN_ADDRESS_UNREACHABLE")
    config = json.loads(args.target_config.read_text())
    targets = [target for target in config["targets"] if target.get("platform") == "ios" and target.get("enabled", True)]
    if len(targets) != 1:
        raise AudioOutputError("AUDIO_OUTPUT_EXACTLY_ONE_IOS_TARGET_REQUIRED")
    target = targets[0]
    caps = dict(target["capabilities"])
    if not caps.get("appium:udid") or caps.get("appium:bundleId") != target["appId"]:
        raise AudioOutputError("AUDIO_OUTPUT_PHYSICAL_TARGET_INVALID")
    contract = target.get("testBuild", {})
    directory = contract.get("resultsDirectory", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", directory):
        raise AudioOutputError("AUDIO_OUTPUT_RESULTS_DIRECTORY_INVALID")
    caps.pop("appium:app", None)
    caps.update({"appium:autoLaunch": False, "appium:noReset": True, "appium:fullReset": False,
                 "appium:enforceAppInstall": False, "appium:forceAppLaunch": False,
                 "appium:shouldTerminateApp": False, "appium:autoAcceptAlerts": False,
                 "appium:autoDismissAlerts": False, "appium:newCommandTimeout": 180})
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    run = {"id": "output-" + secrets.token_hex(16), "challenges": [secrets.token_hex(16) for _ in range(3)],
           "permission": 1 if args.microphone_decision == "allow" else 2}
    result = {"schemaVersion": 1, "runId": run["id"], "passed": False,
              "sourceRevision": args.source_revision, "producerArtifactSha256": args.producer_artifact_sha256,
              "installationBinding": "Operator-pinned candidate and exact reported build version; no installed-byte attestation",
              "testedAtUtc": datetime.now(timezone.utc).isoformat(), "microphoneDecision": args.microphone_decision,
              "proof": "PCM pulled by the physical output sink at system volume zero; no acoustic capture",
              "limitations": ["Does not measure emitted sound or attest installed signed bytes."]}
    normal = {"bundleId": target["appId"], "arguments": ["--url", "file:///~/serverless/tutorial.json"], "environment": {}}
    session = None
    document = None
    try:
        with ExitStack() as stack:
            paths = [Path.home() / ".local/state/overte-ipad-install/installation.lock", *(args.lock_file or [])]
            for path in sorted(set(paths)):
                path.parent.mkdir(parents=True, exist_ok=True)
                lock = stack.enter_context(path.open("a"))
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            url = stack.enter_context(serve_script(str(address), run))
            client = WebDriver(target["serverUrl"])
            connected = client.call("POST", "/session", {"capabilities": {"alwaysMatch": caps, "firstMatch": [{}]}})
            session = connected["sessionId"]
            try:
                handle_permission(client, session, args.microphone_decision, required=False, timeout=0.5)
                client.execute(session, "mobile: terminateApp", {"bundleId": target["appId"]})
                client.execute(session, "mobile: launchApp", normal)
                handle_permission(client, session, args.microphone_decision, required=False, timeout=12)
                if args.reset_microphone:
                    if client.execute(session, "mobile: activeAppInfo").get("bundleId") != target["appId"]:
                        raise AudioOutputError("AUDIO_OUTPUT_TARGET_NOT_FOREGROUND")
                    client.execute(session, "mobile: resetPermission", {"service": "microphone"})
                    client.execute(session, "mobile: terminateApp", {"bundleId": target["appId"]})
                    client.execute(session, "mobile: launchApp", normal)
                    print("Waiting for the microphone dialog; other test actions suspended.", flush=True)
                    result["permissionDialogAnswered"] = handle_permission(
                        client, session, args.microphone_decision, required=True, timeout=60)
                client.execute(session, "mobile: terminateApp", {"bundleId": target["appId"]})
                started = time.time() * 1000
                client.execute(session, "mobile: launchApp", {**normal, "arguments": normal["arguments"] +
                    ["--testScript", url, "--testResultsLocation", directory]})
                identity = None
                deadline = time.monotonic() + 150
                remote = f"@{target['appId']}:documents/{directory}/output-playback-result.json"
                print("Testing microphone transitions without a test tone, then quiet control and three output signals at volume zero.", flush=True)
                while time.monotonic() < deadline:
                    active = client.execute(session, "mobile: activeAppInfo")
                    if active.get("bundleId") != target["appId"]:
                        if identity is None and time.monotonic() < deadline - 140:
                            time.sleep(0.5)
                            continue
                        raise AudioOutputError("AUDIO_OUTPUT_TARGET_LEFT_FOREGROUND")
                    pid = active.get("pid")
                    if type(pid) is not int or pid <= 0 or identity is not None and identity != pid:
                        raise AudioOutputError("AUDIO_OUTPUT_PROCESS_CHANGED")
                    identity = pid
                    try:
                        observed = json.loads(appium_read(client, session, remote))
                    except (RuntimeError, ValueError, WebDriverRequestError):
                        time.sleep(1)
                        continue
                    if observed.get("runId") != run["id"]:
                        time.sleep(1)
                        continue
                    if (type(observed.get("startedEpochMs")) not in (int, float)
                            or observed["startedEpochMs"] < started - 30000
                            or observed["startedEpochMs"] > time.time() * 1000 + 30000):
                        raise AudioOutputError("AUDIO_OUTPUT_STALE_RESULT")
                    document = observed
                    if observed.get("buildVersion") != args.expected_build_version:
                        raise AudioOutputError("AUDIO_OUTPUT_INSTALLED_VERSION_MISMATCH")
                    with tempfile.TemporaryDirectory(prefix="overte-output-pcm-") as private:
                        result.update(evaluate(observed, run, Path(private)))
                    break
                else:
                    raise AudioOutputError("AUDIO_OUTPUT_RESULT_TIMEOUT")
            finally:
                # Do not kill a probe before it has restored the saved settings.
                try:
                    if document and document.get("cleanup", {}).get("restored") is True:
                        wait_capture_removal(client, session, remote, run["id"])
                        result["onDeviceCaptureRemoved"] = True
                        client.execute(session, "mobile: terminateApp", {"bundleId": target["appId"]})
                        client.execute(session, "mobile: launchApp", normal)
                        restore_deadline = time.monotonic() + 10
                        while time.monotonic() < restore_deadline:
                            active = client.execute(session, "mobile: activeAppInfo")
                            if active.get("bundleId") == target["appId"] and active.get("pid") != identity:
                                break
                            time.sleep(0.5)
                        else:
                            raise AudioOutputError("AUDIO_OUTPUT_NORMAL_RELAUNCH_UNVERIFIED")
                        result["normalLaunchRestored"] = True
                finally:
                    if session:
                        client.call("DELETE", "/session/" + session)
    except (Exception, SystemExit) as error:
        result["error"] = str(error).replace("ACOUSTIC_", "AUDIO_OUTPUT_") if isinstance(error, AcousticError) else "AUDIO_OUTPUT_INFRASTRUCTURE_FAILED"
        result["passed"] = False
    finally:
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: internal output and mute at system volume zero." if result["passed"] else "FAIL: internal output verification did not pass.")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, SystemExit) as error:
        if isinstance(error, SystemExit):
            raise
        print("AUDIO_OUTPUT_CONFIGURATION_REJECTED", file=sys.stderr)
        raise SystemExit(2)
