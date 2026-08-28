#!/usr/bin/env python3
"""Own an ephemeral domain-server and assignment-client E2E fixture."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
import uuid


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[2]
MANIFEST_PATH = ROOT / "domain-manifest.json"
MARKER = re.compile(r"OVERTE_E2E_DOMAIN_[A-Z]+(?![A-Z_])")
HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


def validate_domain_fixture() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1:
        raise ValueError("unsupported domain fixture schema")
    expected = {
        "schemaVersion", "bootstrapScript", "expectedEntityCount", "requiredMarkers",
        "spawnPath", "spawnPosition", "minimumFloorThickness", "externalResources",
    }
    if set(manifest) != expected:
        raise ValueError("domain fixture manifest contains unsupported fields")
    script_name = manifest.get("bootstrapScript")
    if (not isinstance(script_name, str) or Path(script_name).name != script_name
            or not script_name.endswith(".js")):
        raise ValueError("domain fixture bootstrap script is invalid")
    script_path = ROOT / script_name
    script = script_path.read_text(encoding="utf-8")
    markers = manifest.get("requiredMarkers")
    if (not isinstance(markers, list) or not markers
            or markers != sorted(set(markers))
            or not all(isinstance(item, str) and MARKER.fullmatch(item) for item in markers)):
        raise ValueError("domain fixture markers must be a sorted unique allowlist")
    if sorted(set(MARKER.findall(script))) != markers:
        raise ValueError("domain bootstrap marker set does not match its manifest")
    if manifest.get("expectedEntityCount") != len(markers):
        raise ValueError("domain fixture entity count does not match its markers")
    spawn = manifest.get("spawnPosition")
    if (not isinstance(spawn, dict) or set(spawn) != {"x", "y", "z"}
            or not all(isinstance(spawn[axis], (int, float)) and not isinstance(spawn[axis], bool)
                       for axis in ("x", "y", "z"))
            or spawn["y"] < 2.0):
        raise ValueError("domain fixture spawn must be safely above the floor")
    expected_path = f"/{spawn['x']},{spawn['y']},{spawn['z']}/0,0,0,1"
    if manifest.get("spawnPath") != expected_path:
        raise ValueError("domain fixture spawn path and position disagree")
    if (not isinstance(manifest.get("minimumFloorThickness"), (int, float))
            or manifest["minimumFloorThickness"] < 0.5
            or manifest.get("externalResources") is not False):
        raise ValueError("domain fixture must be local and use a thick floor")
    if "Entities.addEntity(properties, \"domain\")" not in script:
        raise ValueError("domain bootstrap must create domain entities")
    if "Entities.serversExist() || !Entities.canRez()" not in script:
        raise ValueError("domain bootstrap must wait for entity server permissions")
    if 'Script.resolvePath("domain-ready")' not in script:
        raise ValueError("domain bootstrap must report readiness to its fixture controller")
    return manifest


class DomainResourceHandler(SimpleHTTPRequestHandler):
    bootstrap_path = ""
    content_ready = threading.Event()
    expected_marker_count = 0

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            payload = b'{"ready":true,"schemaVersion":1}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path != self.bootstrap_path:
            self.send_error(404)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/domain-ready":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_error(400)
            return
        if not 1 <= length <= 256:
            self.send_error(400)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400)
            return
        if payload != {"schemaVersion": 1, "markerCount": self.expected_marker_count}:
            self.send_error(400)
            return
        self.content_ready.set()
        self.send_response(204)
        self.end_headers()

    def log_message(self, format_string: str, *arguments: object) -> None:
        print("domain-fixture-http: " + format_string % arguments, file=sys.stderr)


def executable(value: str | None, label: str) -> Path:
    if not value:
        raise ValueError(f"{label} is required")
    path = Path(value).expanduser().resolve()
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"{label} must be an executable regular file")
    return path


def private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPOSITORY or REPOSITORY in resolved.parents:
        raise ValueError("domain fixture output must be outside the source worktree")
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise ValueError("domain fixture output must be absent or empty")
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(resolved, 0o700)
    return resolved


def process_options(environment: dict[str, str], log) -> dict:
    options = {"env": environment, "stdin": subprocess.DEVNULL,
               "stdout": log, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return options


def stop_process(process: subprocess.Popen | None, grace_seconds: int = 5) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=grace_seconds)


def wait_for_domain(process: subprocess.Popen, url: str, timeout_seconds: int) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_error = "domain HTTP endpoint was unavailable"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("domain-server exited before becoming ready")
        try:
            with urlopen(url, timeout=1) as response:
                value = response.read(128).decode("ascii").strip()
            return str(uuid.UUID(value))
        except (OSError, UnicodeError, ValueError) as error:
            last_error = str(error)
            time.sleep(0.1)
    raise RuntimeError(f"domain-server readiness timed out: {last_error}")


def wait_for_assignment_content(processes: tuple[subprocess.Popen, ...], log_path: Path,
                                expected_count: int, timeout_seconds: int,
                                stopping: threading.Event | None = None,
                                content_ready: threading.Event | None = None) -> None:
    marker = f"OVERTE_E2E_DOMAIN_FIXTURE_READY markers={expected_count}"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if content_ready is not None and content_ready.is_set():
            return
        if stopping is not None and stopping.is_set():
            raise RuntimeError("domain fixture stopped before content became ready")
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("domain fixture process exited before content became ready")
        try:
            if marker in log_path.read_text(encoding="utf-8"):
                return
        except OSError:
            pass
        time.sleep(0.1)
    raise RuntimeError("assignment-owned domain content did not become ready")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain-server")
    parser.add_argument("--assignment-client")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--public-host")
    parser.add_argument("--domain-host")
    parser.add_argument("--domain-port", type=int, default=40102)
    parser.add_argument("--http-port", type=int, default=40100)
    parser.add_argument("--script-port", type=int, default=0)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--startup-timeout-seconds", type=int, default=60)
    parser.add_argument("--assignment-warmup-seconds", type=float, default=2.0)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name in ("domain_port", "http_port"):
        if not 1 <= getattr(args, name) <= 65535:
            parser.error(f"--{name.replace('_', '-')} must be from 1 through 65535")
    if not 0 <= args.script_port <= 65535:
        parser.error("--script-port must be from 0 through 65535")
    if args.script_port != 0 and args.script_port == args.http_port:
        parser.error("--script-port and --http-port must differ")
    if not 1 <= args.startup_timeout_seconds <= 300:
        parser.error("--startup-timeout-seconds must be from 1 through 300")
    if not 0.0 <= args.assignment_warmup_seconds <= 30.0:
        parser.error("--assignment-warmup-seconds must be from 0 through 30")
    return args


def main() -> int:
    args = parse_args()
    manifest = validate_domain_fixture()
    if args.check:
        print(f"PASS: domain fixture defines {manifest['expectedEntityCount']} assignment-owned markers")
        return 0
    domain_server = executable(args.domain_server, "--domain-server")
    assignment_client = executable(args.assignment_client, "--assignment-client")
    if args.output_dir is None:
        raise ValueError("--output-dir is required")
    output = private_output(args.output_dir)
    public_host = args.public_host or args.bind
    if public_host in {"0.0.0.0", "::"}:
        raise ValueError("--public-host is required when binding all interfaces")
    domain_host = args.domain_host or public_host
    for value, label in ((public_host, "--public-host"), (domain_host, "--domain-host")):
        if not HOST.fullmatch(value) or ".." in value:
            raise ValueError(f"{label} must be a DNS name or IPv4 address")

    DomainResourceHandler.bootstrap_path = f"/{manifest['bootstrapScript']}"
    DomainResourceHandler.content_ready = threading.Event()
    DomainResourceHandler.expected_marker_count = manifest["expectedEntityCount"]
    handler = partial(DomainResourceHandler, directory=str(ROOT))
    resources = ThreadingHTTPServer((args.bind, args.script_port), handler)
    resource_thread = threading.Thread(target=resources.serve_forever, daemon=True)
    resource_thread.start()
    resource_base = f"http://{public_host}:{resources.server_address[1]}"
    script_url = f"{resource_base}/{manifest['bootstrapScript']}"

    config = {
        "version": 2.2,
        "metaverse": {
            "automatic_networking": "disabled",
            "enable_packet_verification": False,
            "local_port": args.domain_port,
        },
        "scripts": {"persistent_scripts": [{
            "url": script_url, "num_instances": 1, "pool": "overte-e2e-domain",
        }]},
    }
    config_path = output / "domain-config.json"
    atomic_json(config_path, config)
    runtime = output / "runtime"
    for name in ("config", "data", "cache"):
        (runtime / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = os.environ.copy()
    environment.update({
        "XDG_CONFIG_HOME": str(runtime / "config"),
        "XDG_DATA_HOME": str(runtime / "data"),
        "XDG_CACHE_HOME": str(runtime / "cache"),
        "HIFI_DOMAIN_SERVER_PORT": str(args.domain_port),
        "HIFI_DOMAIN_SERVER_HTTP_PORT": str(args.http_port),
        "OVERTE_DOMAIN_SERVER_WS_PORT": str(args.domain_port),
    })

    domain_log = (output / "domain-server.log").open("w", encoding="utf-8")
    assignment_log = (output / "assignment-client.log").open("w", encoding="utf-8")
    assignment_agent_log = (output / "assignment-agent.log").open("w", encoding="utf-8")
    (output / "assignment-logs").mkdir(mode=0o700)
    domain_process = assignment_agent_process = None
    assignment_processes: list[subprocess.Popen] = []
    stopping = threading.Event()

    def request_stop(_signal=None, _frame=None) -> None:
        stopping.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
    try:
        domain_process = subprocess.Popen(
            [str(domain_server), "--user-config", str(config_path),
             "--logOptions", "nocolor,process_id,milliseconds"],
            **process_options(environment, domain_log))
        domain_id = wait_for_domain(
            domain_process, f"http://127.0.0.1:{args.http_port}/id",
            args.startup_timeout_seconds)
        for assignment_type in ("0", "1", "3", "4", "5", "6"):
            assignment_processes.append(subprocess.Popen(
                [str(assignment_client), "-t", assignment_type, "-a", "127.0.0.1",
                 "--server-port", str(args.domain_port),
                 "--disable-domain-port-auto-discovery",
                 "--log-directory", str(output / "assignment-logs"),
                 "--logOptions", "nocolor,process_id,milliseconds"],
                **process_options(environment, assignment_log)))
        assignment_agent_process = subprocess.Popen(
            [str(assignment_client), "-t", "2", "--pool", "overte-e2e-domain",
             "-a", "127.0.0.1", "--server-port", str(args.domain_port),
             "--disable-domain-port-auto-discovery",
             "--log-directory", str(output / "assignment-logs"),
             "--logOptions", "nocolor,process_id,milliseconds"],
            **process_options(environment, assignment_agent_log))
        deadline = time.monotonic() + args.assignment_warmup_seconds
        while time.monotonic() < deadline:
            if (domain_process.poll() is not None
                    or any(process.poll() is not None for process in assignment_processes)
                    or assignment_agent_process.poll() is not None):
                raise RuntimeError("domain fixture process exited during assignment warmup")
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        fixture_processes = (
            domain_process, *assignment_processes, assignment_agent_process)
        wait_for_assignment_content(
            fixture_processes,
            output / "assignment-agent.log", manifest["expectedEntityCount"],
            args.startup_timeout_seconds, stopping, DomainResourceHandler.content_ready)
        ready = {
            "schemaVersion": 1,
            "domainUrl": f"hifi://{domain_host}:{args.domain_port}{manifest['spawnPath']}",
            "domainHost": domain_host,
            "domainId": domain_id,
            "requiredMarkers": manifest["requiredMarkers"],
            "expectedEntityCount": manifest["expectedEntityCount"],
            "bootstrapScriptUrl": script_url,
        }
        if args.ready_file:
            atomic_json(args.ready_file.resolve(), ready)
        print(json.dumps(ready, sort_keys=True), flush=True)
        while not stopping.wait(0.25):
            if domain_process.poll() is not None:
                raise RuntimeError("domain-server exited while fixture was active")
            if any(process.poll() is not None for process in assignment_processes):
                raise RuntimeError("assignment-client exited while fixture was active")
            if assignment_agent_process.poll() is not None:
                raise RuntimeError("assignment agent exited while fixture was active")
    finally:
        stop_process(assignment_agent_process)
        for assignment_process in reversed(assignment_processes):
            stop_process(assignment_process)
        stop_process(domain_process)
        resources.shutdown()
        resources.server_close()
        resource_thread.join(timeout=2)
        assignment_log.close()
        assignment_agent_log.close()
        domain_log.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
