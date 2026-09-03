#!/usr/bin/env python3
"""Own every controlled E2E fixture and publish one private environment file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
DEVICE_ROOT = ROOT.parent
REPOSITORY = DEVICE_ROOT.parents[1]


def atomic_json(path: Path, value: dict, private: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)
    if private:
        os.chmod(path, 0o600)


def wait_json(path: Path, process: subprocess.Popen, timeout: float, label: str) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("schemaVersion") == 1:
                return value
            raise RuntimeError(f"{label} returned invalid ready metadata")
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited before becoming ready")
        time.sleep(0.05)
    raise RuntimeError(f"{label} readiness timed out")


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except OSError:
            process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def environment(scene: dict, domain: dict | None) -> dict[str, str]:
    asset = scene["asset"]
    sound = scene["sound"]
    values = {
        "OVERTE_E2E_SCENE_URL": scene["sceneUrl"],
        "OVERTE_E2E_ASSET_ID": asset["id"],
        "OVERTE_E2E_ASSET_URL": asset["url"],
        "OVERTE_E2E_ASSET_TELEMETRY_URL": asset["telemetryUrl"],
        "OVERTE_E2E_ASSET_CONTENT_TYPE": asset["contentType"],
        "OVERTE_E2E_ASSET_SHA256": asset["sha256"],
        "OVERTE_E2E_ASSET_BYTES": str(asset["bytes"]),
        "OVERTE_E2E_ASSET_WIDTH": str(asset["width"]),
        "OVERTE_E2E_ASSET_HEIGHT": str(asset["height"]),
        "OVERTE_E2E_ASSET_ENTITY_NAME": asset["entityName"],
        "OVERTE_E2E_SOUND_URL": scene["soundUrl"],
        "OVERTE_E2E_SOUND_COMMAND_URL": scene["soundCommandUrl"],
        "OVERTE_E2E_SOUND_REQUESTS_URL": scene["soundRequestsUrl"],
        "OVERTE_E2E_SOUND_DURATION_SECONDS": str(sound["durationSeconds"]),
        "OVERTE_E2E_PROBE_SCRIPT_URL": scene["probeScriptUrl"],
        "OVERTE_E2E_CLIENT_COMMAND_URL": scene["clientCommandUrl"],
    }
    if domain is not None:
        values.update({
            "OVERTE_E2E_DOMAIN_URL": domain["domainUrl"],
            "OVERTE_E2E_DOMAIN_HOST": domain["domainHost"],
            "OVERTE_E2E_DOMAIN_ID": domain["domainId"],
            "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(
                domain["requiredMarkers"], separators=(",", ":")),
            "OVERTE_E2E_DOMAIN_CONTROL_URL": domain["controlUrl"],
            "OVERTE_E2E_DOMAIN_CONTROL_TOKEN": domain["controlToken"],
        })
    if not all(isinstance(key, str) and isinstance(value, str) and value
               for key, value in values.items()):
        raise RuntimeError("fixture ready metadata contains an invalid environment value")
    return dict(sorted(values.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--public-host")
    parser.add_argument("--fixture-port", type=int, default=0)
    parser.add_argument("--scene-only", action="store_true")
    parser.add_argument("--domain-server")
    parser.add_argument("--assignment-client")
    parser.add_argument("--domain-port", type=int, default=40102)
    parser.add_argument("--domain-http-port", type=int, default=40100)
    parser.add_argument("--startup-timeout-seconds", type=int, default=45)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.startup_timeout_seconds <= 300:
        parser.error("--startup-timeout-seconds must be from 1 through 300")
    if args.scene_only and (args.domain_server or args.assignment_client):
        parser.error("--scene-only cannot be combined with domain executables")
    if not args.scene_only and not args.check and (
            not args.domain_server or not args.assignment_client):
        parser.error("domain executables are required unless --scene-only is selected")
    return args


def main() -> int:
    args = parse_args()
    if args.check:
        for script in (ROOT / "serve.py", ROOT / "domain.py"):
            result = subprocess.run([sys.executable, str(script), "--check"],
                                    text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=False)
            if result.returncode:
                raise RuntimeError(result.stdout.strip())
        print("PASS: unified fixture orchestrator contracts are valid")
        return 0
    if args.output_dir is None:
        raise ValueError("--output-dir is required")
    output = args.output_dir.expanduser().resolve()
    if output == REPOSITORY or REPOSITORY in output.parents:
        raise ValueError("fixture orchestration output must be outside the worktree")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("fixture orchestration output must be absent or empty")
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(output, 0o700)
    log = (output / "orchestrator.log").open("w", encoding="utf-8")
    scene_process = domain_process = None
    stopping = False

    def request_stop(_signal=None, _frame=None) -> None:
        nonlocal stopping
        stopping = True

    handled_signals = [signal.SIGTERM, signal.SIGINT]
    if hasattr(signal, "SIGBREAK"):
        handled_signals.append(signal.SIGBREAK)
    for handled_signal in handled_signals:
        signal.signal(handled_signal, request_stop)
    try:
        scene_ready_path = output / "scene-ready.json"
        command = [sys.executable, str(ROOT / "serve.py"), "--bind", args.bind,
                   "--port", str(args.fixture_port), "--ready-file", str(scene_ready_path)]
        if args.public_host:
            command += ["--public-host", args.public_host]
        popen_options = {"stdin": subprocess.DEVNULL, "stdout": log,
                         "stderr": subprocess.STDOUT}
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True
        scene_process = subprocess.Popen(command, **popen_options)
        scene = wait_json(scene_ready_path, scene_process,
                          args.startup_timeout_seconds, "serverless fixture")
        domain = None
        if not args.scene_only:
            domain_ready_path = output / "domain-ready.json"
            domain_output = output / "domain"
            command = [
                sys.executable, str(ROOT / "domain.py"),
                "--domain-server", args.domain_server,
                "--assignment-client", args.assignment_client,
                "--bind", args.bind,
                "--domain-port", str(args.domain_port),
                "--http-port", str(args.domain_http_port),
                "--output-dir", str(domain_output),
                "--ready-file", str(domain_ready_path),
            ]
            if args.public_host:
                command += ["--public-host", args.public_host,
                            "--domain-host", args.public_host]
            popen_options = {"stdin": subprocess.DEVNULL, "stdout": log,
                             "stderr": subprocess.STDOUT}
            if os.name == "nt":
                popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_options["start_new_session"] = True
            domain_process = subprocess.Popen(command, **popen_options)
            domain = wait_json(domain_ready_path, domain_process,
                               args.startup_timeout_seconds, "domain fixture")
        env_path = output / "environment.json"
        values = environment(scene, domain)
        atomic_json(env_path, {"schemaVersion": 1, "environment": values})
        ready = {
            "schemaVersion": 1,
            "environmentFile": str(env_path),
            "sceneReady": True,
            "domainReady": domain is not None,
        }
        if args.ready_file:
            atomic_json(args.ready_file.resolve(), ready)
        print(json.dumps(ready, sort_keys=True), flush=True)
        while not stopping:
            if scene_process.poll() is not None:
                raise RuntimeError("serverless fixture exited while active")
            if domain_process is not None and domain_process.poll() is not None:
                raise RuntimeError("domain fixture exited while active")
            time.sleep(0.2)
    finally:
        stop(domain_process)
        stop(scene_process)
        log.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
