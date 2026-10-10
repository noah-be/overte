#!/usr/bin/env python3
"""Measure built-in iPad speaker-to-microphone audio, without external hardware."""
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
from voice_peer.voice_signal import analyze  # noqa: E402


class AcousticError(RuntimeError):
    """Only closed, privacy-safe diagnostics cross the CLI boundary."""


def evaluate(document: dict, run: dict, private: Path) -> dict:
    errors = {"acoustic-test-build-required": "ACOUSTIC_NEW_TEST_BUILD_REQUIRED",
              "acoustic-microphone-permission-denied": "ACOUSTIC_MICROPHONE_PERMISSION_DENIED",
              "acoustic-route-or-mode-changed": "ACOUSTIC_ROUTE_OR_MODE_CHANGED",
              "acoustic-permission-or-lifecycle-changed": "ACOUSTIC_PERMISSION_OR_LIFECYCLE_CHANGED",
              "acoustic-built-in-input-unavailable": "ACOUSTIC_BUILT_IN_INPUT_UNAVAILABLE"}
    if isinstance(document, dict) and document.get("error") in errors:
        raise AcousticError(errors[document["error"]])
    if (not isinstance(document, dict) or document.get("runId") != run["id"]
            or document.get("schemaVersion") != 1 or document.get("ok") is not True
            or document.get("cleanup", {}).get("restored") is not True
            or document.get("playbackStarted") is not True):
        raise AcousticError("ACOUSTIC_RUN_OR_CLEANUP_FAILED")
    captures = document.get("captures")
    if not isinstance(captures, list) or len(captures) != 2:
        raise AcousticError("ACOUSTIC_CAPTURES_MISSING")
    measurements = []
    for capture, kind, challenge in zip(captures, ("control", "playback"), (run["control"], run["signal"])):
        if (not isinstance(capture, dict) or capture.get("kind") != kind
                or capture.get("challenge") != challenge
                or capture.get("captureSource") != "physical-device-input-before-processing"
                or any(capture.get(key) is not True for key in (
                    "ok", "captureComplete", "physicalDevice", "builtInMicrophone", "builtInSpeaker",
                    "measurementMode", "iosForeground", "iosCaptureAllowed", "inputPresent"))
                or any(capture.get(key) is not False for key in (
                    "captureInvalid", "sourceEnabled", "sourceClockActive", "iosInterrupted", "nativeMuted"))
                or capture.get("iosPermission") != 1 or capture.get("inputState") != 0
                or capture.get("inputError") != 0
                or type(capture.get("physicalInputCallbacks")) is not int
                or capture["physicalInputCallbacks"] < 1):
            raise AcousticError("ACOUSTIC_PHYSICAL_CAPTURE_INVALID")
        data = wav(capture)
        path = private / (kind + ".wav")
        path.write_bytes(data)
        path.chmod(0o600)
        with wave.open(str(path), "rb") as source:
            if (source.getframerate() != capture.get("captureRate")
                    or source.getnchannels() != capture.get("captureChannels")
                    or source.getnframes() != 8 * source.getframerate()
                    or capture.get("captureBytes") != source.getnframes() * source.getnchannels() * 2):
                raise AcousticError("ACOUSTIC_CAPTURE_FORMAT_MISMATCH")
        measured = analyze(path, challenge, "present" if kind == "playback" else "absent")
        if kind == "control":
            # Ambient speech/noise need not be digital silence. The negative
            # control must contain a complete real capture without this nonce.
            measured["passed"] = measured["completeCapture"] and not measured["patternDetected"]
        measured["proof"] = "Physical built-in speaker-to-microphone capture before processing"
        measured["kind"] = kind
        measured["captureSha256"] = capture["sha256"]
        measured["nativeStatus"] = {key: capture[key] for key in (
            "captureSource", "physicalDevice", "builtInMicrophone", "builtInSpeaker", "measurementMode",
            "iosPermission", "iosForeground", "iosCaptureAllowed", "iosInterrupted", "nativeMuted",
            "sourceEnabled", "sourceClockActive", "inputPresent", "inputState", "inputError",
            "captureComplete", "captureInvalid", "physicalInputCallbacks", "captureRate", "captureChannels", "captureBytes")}
        measurements.append(measured)
    return {"schemaVersion": 1, "runId": run["id"],
            "passed": all(item["passed"] for item in measurements),
            "physicalAudioHardwareTested": True, "measurements": measurements,
            "startedEpochMs": document.get("startedEpochMs"), "completedEpochMs": document.get("completedEpochMs"),
            "deviceBuildVersion": document.get("buildVersion"), "cleanup": document["cleanup"],
            "limitations": ["No calibrated sound-pressure or subjective speech-quality measurement.",
                            "Built-in speaker and microphone are tested together in measurement mode.",
                            "Denied permission and ordinary voice/AEC behavior require separate checks."]}


def handle_permission(client, session: str, decision: str, *, required: bool, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            text = client.call("GET", f"/session/{session}/alert/text")
        except WebDriverRequestError as error:
            if error.status != 404:
                raise AcousticError("ACOUSTIC_ALERT_QUERY_FAILED") from None
            time.sleep(0.5)
            continue
        if not isinstance(text, str) or not any(word in text.lower() for word in ("mikrofon", "microphone")):
            raise AcousticError("ACOUSTIC_UNEXPECTED_SYSTEM_DIALOG")
        buttons = client.execute(session, "mobile: alert", {"action": "getButtons"})
        labels = ("Erlauben", "Allow", "OK") if decision == "allow" else ("Nicht erlauben", "Don't Allow", "Don’t Allow")
        label = next((value for value in labels if value in buttons), None)
        if label is None:
            raise AcousticError("ACOUSTIC_PERMISSION_BUTTON_UNAVAILABLE")
        client.execute(session, "mobile: alert", {"action": "accept" if decision == "allow" else "dismiss", "buttonLabel": label})
        try:
            client.call("GET", f"/session/{session}/alert/text")
        except WebDriverRequestError as error:
            if error.status == 404:
                print("Microphone dialog answered and closed; subsequent test actions now permitted.", flush=True)
                return True
            raise AcousticError("ACOUSTIC_ALERT_QUERY_FAILED") from None
        raise AcousticError("ACOUSTIC_PERMISSION_DIALOG_STILL_OPEN")
    if required:
        raise AcousticError("ACOUSTIC_REQUIRED_PERMISSION_DIALOG_MISSING")
    return False


def wait_capture_removal(client, session: str, remote: str, run_id: str, timeout: float = 60) -> None:
    """Do not terminate the script before its on-device WAV expiry runs."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            receipt = json.loads(appium_read(client, session, remote))
        except (RuntimeError, ValueError, WebDriverRequestError):
            time.sleep(1)
            continue
        if (receipt.get("runId") == run_id
                and receipt.get("cleanup", {}).get("restored") is True
                and not any("wavBase64" in capture for capture in receipt.get("captures", []))):
            return
        time.sleep(1)
    raise AcousticError("ACOUSTIC_TRANSFER_CLEANUP_FAILED")


@contextmanager
def serve_script(address: str, run: dict):
    # Serve exactly one generated script. No directory listings, private target
    # configuration, recordings or result files are exposed over HTTP.
    body = ("var OVERTE_ACOUSTIC_RUN = " + json.dumps(run) + ";\n").encode() + Path(__file__).with_suffix(".js").read_bytes()
    route = "/" + run["id"] + ".js"
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != route:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer((address, 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{address}:{server.server_port}{route}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
        raise AcousticError("ACOUSTIC_CANDIDATE_IDENTITY_INVALID")
    address = ipaddress.IPv4Address(args.listen_address)
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise AcousticError("ACOUSTIC_LISTEN_ADDRESS_UNREACHABLE")
    config = json.loads(args.target_config.read_text())
    targets = [target for target in config["targets"] if target.get("platform") == "ios" and target.get("enabled", True)]
    if len(targets) != 1:
        raise AcousticError("ACOUSTIC_EXACTLY_ONE_IOS_TARGET_REQUIRED")
    target = targets[0]
    caps = dict(target["capabilities"])
    if not caps.get("appium:udid") or caps.get("appium:bundleId") != target["appId"]:
        raise AcousticError("ACOUSTIC_PHYSICAL_TARGET_INVALID")
    contract = target.get("testBuild", {})
    directory = contract.get("resultsDirectory", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", directory):
        raise AcousticError("ACOUSTIC_RESULTS_DIRECTORY_INVALID")
    caps.pop("appium:app", None)
    caps.update({"appium:autoLaunch": False, "appium:noReset": True, "appium:fullReset": False,
                 "appium:enforceAppInstall": False, "appium:forceAppLaunch": False,
                 "appium:shouldTerminateApp": False, "appium:autoAcceptAlerts": False,
                 "appium:autoDismissAlerts": False, "appium:newCommandTimeout": 180})
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    run = {"id": "acoustic-" + secrets.token_hex(16), "control": secrets.token_hex(16), "signal": secrets.token_hex(16)}
    result = {"schemaVersion": 1, "runId": run["id"], "passed": False,
              "sourceRevision": args.source_revision, "producerArtifactSha256": args.producer_artifact_sha256,
              "installationBinding": "Operator-pinned candidate and exact reported build version; no installed-byte attestation",
              "testedAtUtc": datetime.now(timezone.utc).isoformat()}
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
                        raise AcousticError("ACOUSTIC_TARGET_NOT_FOREGROUND")
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
                remote = f"@{target['appId']}:documents/{directory}/acoustic-result.json"
                print("Internal acoustic test running: quiet control, then fresh speaker challenge.", flush=True)
                while time.monotonic() < deadline:
                    active = client.execute(session, "mobile: activeAppInfo")
                    if active.get("bundleId") != target["appId"]:
                        raise AcousticError("ACOUSTIC_TARGET_LEFT_FOREGROUND")
                    pid = active.get("pid")
                    if type(pid) is not int or pid <= 0 or identity is not None and identity != pid:
                        raise AcousticError("ACOUSTIC_PROCESS_CHANGED")
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
                        raise AcousticError("ACOUSTIC_STALE_RESULT")
                    document = observed
                    if observed.get("buildVersion") != args.expected_build_version:
                        raise AcousticError("ACOUSTIC_INSTALLED_VERSION_MISMATCH")
                    with tempfile.TemporaryDirectory(prefix="overte-acoustic-pcm-") as private:
                        result.update(evaluate(observed, run, Path(private)))
                    break
                else:
                    raise AcousticError("ACOUSTIC_RESULT_TIMEOUT")
            finally:
                # Do not kill a probe before it has restored the saved settings.
                try:
                    if document and document.get("cleanup", {}).get("restored") is True:
                        wait_capture_removal(client, session, remote, run["id"])
                        result["onDeviceCaptureRemoved"] = True
                        client.execute(session, "mobile: terminateApp", {"bundleId": target["appId"]})
                        client.execute(session, "mobile: launchApp", normal)
                        result["normalLaunchRestored"] = True
                finally:
                    if session:
                        client.call("DELETE", "/session/" + session)
    except (Exception, SystemExit) as error:
        result["error"] = str(error) if isinstance(error, AcousticError) else "ACOUSTIC_INFRASTRUCTURE_FAILED"
        result["passed"] = False
    finally:
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: internal acoustic challenge detected." if result["passed"] else "FAIL: internal acoustic verification did not pass.")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, SystemExit) as error:
        if isinstance(error, SystemExit):
            raise
        print("ACOUSTIC_CONFIGURATION_REJECTED", file=sys.stderr)
        raise SystemExit(2)
