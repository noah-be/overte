#!/usr/bin/env python3
"""Linux PC voice-test partner: isolate, send, receive, and verify PCM."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

from runtime import InfrastructureError, serve, stop
from voice_signal import DURATION, FREQUENCIES, analyze, sequence, write_wav


def default_state() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "overte-voice-peer"


def control(root: Path, value: dict) -> dict:
    session_file = root / "session.json"
    if not session_file.is_file():
        raise InfrastructureError("PC voice peer is not running")
    if session_file.stat().st_mode & 0o077 or session_file.stat().st_uid != os.getuid():
        raise InfrastructureError("controller state must be private and owned by the current user")
    session = json.loads(session_file.read_text())
    url = urllib.parse.urlsplit(session["url"])
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.path:
        raise InfrastructureError("controller must use a loopback-only URL")
    request = urllib.request.Request(session["url"] + "/control",
                                     data=json.dumps(value).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + session["token"],
                                              "Content-Type": "application/json"})
    try:
        # Do not forward private loopback credentials through an HTTP proxy.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        data = json.loads(error.read())
        raise InfrastructureError(data.get("error", "PC voice operation failed")) from None
    except (urllib.error.URLError, TimeoutError):
        raise InfrastructureError("PC voice controller is unreachable or timed out") from None


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--state-dir", type=Path, default=default_state())
    commands = result.add_subparsers(dest="action", required=True)
    for name, help_text in (("serve", "own one dedicated Overte client until stopped"),
                            ("start", "start the PC partner in the background and wait for readiness")):
        start = commands.add_parser(name, help=help_text)
        start.add_argument("--client", type=Path)
        start.add_argument("--domain")
        start.add_argument("--client-env", type=Path, help="private JSON with client library/plugin environment")
        start.add_argument("--launch-config", type=Path,
                           help="private JSON with client, domain, and optional clientEnv paths")
    for name in ("status", "stop", "check-local", "check-server"):
        commands.add_parser(name)
    domain_check = commands.add_parser("domain-check", help="compare the connected domain without exporting its private ID")
    domain_check.add_argument("--domain-id", required=True)
    send = commands.add_parser("send", help="send a challenge through the avatar microphone path")
    send.add_argument("--challenge")
    muted_send = commands.add_parser("send-muted", help="send a challenge while microphone mute stays enabled")
    muted_send.add_argument("--challenge", required=True)
    receive = commands.add_parser("receive", help="capture only the owned PC client output and detect a remote challenge")
    receive.add_argument("--challenge", required=True)
    receive.add_argument("--seconds", type=float, default=8)
    receive.add_argument("--expect", choices=("present", "absent"), default="present")
    position = commands.add_parser("position", help="place the muted PC avatar at the device's test location")
    for axis in ("x", "y", "z"):
        position.add_argument("--" + axis, type=float, required=True)
    generate = commands.add_parser("challenge", help="generate a fresh shared challenge WAV for a remote sender")
    generate.add_argument("--challenge")
    generate.add_argument("--output", type=Path, required=True)
    offline = commands.add_parser("analyze", help="analyze a received WAV without a running PC client")
    offline.add_argument("--wav", type=Path, required=True)
    offline.add_argument("--challenge", required=True)
    offline.add_argument("--expect", choices=("present", "absent"), default="present")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.action in ("serve", "start"):
            config = args.launch_config or args.state_dir / "launch-config.json"
            if config.exists():
                if config.stat().st_mode & 0o077 or config.stat().st_uid != os.getuid():
                    raise ValueError("launch configuration must be private and owned by the current user")
                launch = json.loads(config.read_text())
                if not isinstance(launch, dict) or not set(launch) <= {"client", "domain", "clientEnv"}:
                    raise ValueError("invalid launch configuration")
                args.client = args.client or Path(launch["client"])
                args.domain = args.domain or launch.get("domain")
                args.client_env = args.client_env or (Path(launch["clientEnv"]) if launch.get("clientEnv") else None)
            if args.client is None:
                raise ValueError("an executable client or private launch configuration is required")
            args.domain = args.domain or "hifi://overte_hub"
            if args.action == "start":
                try:
                    current = control(args.state_dir, {"action": "status"})
                    if current.get("clientRunning"):
                        print(json.dumps(dict(current, alreadyRunning=True), indent=2))
                        return 0
                except InfrastructureError:
                    pass
                args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                args.state_dir.chmod(0o700)
                log_path = args.state_dir / "supervisor.log"
                child_args = [sys.executable, str(Path(__file__).resolve()), "--state-dir", str(args.state_dir.resolve()),
                              "serve", "--client", str(args.client.resolve()), "--domain", args.domain]
                if args.client_env:
                    child_args.extend(["--client-env", str(args.client_env.resolve())])
                with log_path.open("wb") as log:
                    log_path.chmod(0o600)
                    child = subprocess.Popen(child_args, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                             start_new_session=True)
                try:
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        if child.poll() is not None:
                            raise InfrastructureError("PC partner startup failed; inspect the private supervisor log")
                        try:
                            current = control(args.state_dir, {"action": "status"})
                            if current.get("snapshotFresh") and current.get("audioRouted"):
                                print(json.dumps(dict(current, started=True), indent=2))
                                return 0
                        except InfrastructureError:
                            pass
                        time.sleep(0.25)
                    raise InfrastructureError("PC partner did not become ready within 60 seconds")
                except BaseException:
                    stop(child)
                    raise
            env = {}
            if args.client_env:
                if args.client_env.stat().st_mode & 0o077:
                    raise ValueError("client environment file must have private permissions")
                env = json.loads(args.client_env.read_text())
                allowed = {"LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
                           "QML2_IMPORT_PATH", "QTWEBENGINEPROCESS_PATH", "QT_QPA_PLATFORM"}
                if (not isinstance(env, dict) or not set(env) <= allowed
                        or not all(isinstance(value, str) for value in env.values())):
                    raise ValueError("client environment contains unsupported entries")
            serve(args.state_dir.resolve(), args.client.resolve(), args.domain, env)
            return 0
        if args.action == "challenge":
            challenge = args.challenge or secrets.token_hex(16)
            symbols = sequence(challenge)
            # Avoid silently replacing a previous challenge or unrelated audio.
            with args.output.open("xb"):
                pass
            write_wav(args.output, challenge)
            args.output.chmod(0o600)
            result = {"schemaVersion": 1, "challenge": challenge,
                      "frequenciesHz": [FREQUENCIES[symbol] for symbol in symbols],
                      "durationSeconds": DURATION, "sampleRate": 24000}
        elif args.action == "analyze":
            result = analyze(args.wav, args.challenge, args.expect)
        else:
            request = {"action": args.action}
            for field in ("challenge", "seconds", "expect"):
                if hasattr(args, field):
                    request[field] = getattr(args, field)
            if args.action == "domain-check":
                request["domainId"] = args.domain_id
            if args.action == "position":
                request["position"] = {axis: getattr(args, axis) for axis in ("x", "y", "z")}
            result = control(args.state_dir, request)
            if args.action == "stop":
                deadline = time.monotonic() + 15
                while (args.state_dir / "session.json").exists():
                    if time.monotonic() > deadline:
                        raise InfrastructureError("PC partner cleanup did not finish within 15 seconds")
                    time.sleep(0.1)
                result = {"stopped": True, "privateAudioDevicesRemoved": True}
        print(json.dumps(result, indent=2))
        return 1 if result.get("passed") is False else 0
    except InfrastructureError as error:
        print(json.dumps({"error": str(error), "category": "infrastructure"}), file=sys.stderr)
        return 75
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        # Paths and malformed private file contents stay out of shared output.
        print(json.dumps({"error": "invalid input or unavailable local file", "category": "configuration"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
