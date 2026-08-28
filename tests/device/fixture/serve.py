#!/usr/bin/env python3
"""Serve and validate the deterministic Overte physical-device E2E fixture."""

from __future__ import annotations

import argparse
import base64
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import struct
import sys
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit


ROOT = Path(__file__).resolve().parent
PROBE = ROOT.parent / "probe" / "overte_e2e_probe.js"
URL = re.compile(r"(?:https?|ftp)://", re.IGNORECASE)
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def controlled_scene_url(base_url: str, manifest: dict) -> str:
    return f"{base_url}/{manifest['scene']}?{urlencode({'location': manifest['spawnPath']})}"


def asset_source(manifest: dict) -> Path:
    return (ROOT / manifest["asset"]["source"]).resolve()


def asset_payload(manifest: dict) -> bytes:
    try:
        return base64.b64decode(asset_source(manifest).read_bytes().strip(), validate=True)
    except (OSError, ValueError) as error:
        raise ValueError("controlled asset source is not valid base64") from error


def png_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError("controlled asset must be a PNG with an IHDR header")
    return struct.unpack(">II", payload[16:24])


def validate_fixture() -> dict:
    manifest = json.loads((ROOT / "fixture-manifest.json").read_text(encoding="utf-8"))
    scene = json.loads((ROOT / manifest["scene"]).read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or scene.get("DataVersion") != 3:
        raise ValueError("unsupported fixture or scene schema")
    entities = scene.get("Entities")
    if not isinstance(entities, list) or len(entities) != manifest.get("expectedEntityCount"):
        raise ValueError("fixture entity count does not match its manifest")
    ids = [entity.get("id") for entity in entities]
    names = [entity.get("name") for entity in entities]
    if len(set(ids)) != len(ids) or not all(isinstance(item, str) and item for item in ids):
        raise ValueError("fixture entity IDs must be unique and non-empty")
    if sorted(names) != manifest.get("requiredMarkers"):
        raise ValueError("fixture marker set does not match its manifest")
    if scene.get("Paths", {}).get("/") != manifest.get("spawnPath"):
        raise ValueError("fixture spawn path does not match its manifest")
    spawn = manifest.get("spawnPosition")
    floor = next((entity for entity in entities
                  if entity.get("name") == "OVERTE_E2E_FLOOR"), None)
    if (not isinstance(spawn, dict) or set(spawn) != {"x", "y", "z"}
            or not all(isinstance(spawn[axis], (int, float)) for axis in ("x", "y", "z"))
            or spawn["y"] < 2.0):
        raise ValueError("fixture spawn must be explicit and safely above the floor")
    expected_spawn_path = (f"/{spawn['x']},{spawn['y']},{spawn['z']}"
                           "/0,0,0,1")
    if manifest["spawnPath"] != expected_spawn_path:
        raise ValueError("fixture spawn path and position disagree")
    if not isinstance(floor, dict):
        raise ValueError("fixture floor marker is unavailable")
    dimensions = floor.get("dimensions", {})
    position = floor.get("position", {})
    thickness = dimensions.get("y")
    minimum_thickness = manifest.get("minimumFloorThickness")
    if (not isinstance(thickness, (int, float))
            or not isinstance(minimum_thickness, (int, float))
            or thickness < minimum_thickness
            or not isinstance(position.get("y"), (int, float))
            or abs(position["y"] + thickness / 2.0) > 1e-6):
        raise ValueError("fixture floor must be thick with its top fixed at y=0")
    if manifest.get("externalResources") is not False or URL.search(json.dumps(scene)):
        raise ValueError("controlled fixture must not depend on external resources")
    asset = manifest.get("asset")
    required_asset_fields = {
        "id", "route", "source", "encoding", "contentType", "sha256", "bytes",
        "width", "height", "entityName",
    }
    if not isinstance(asset, dict) or set(asset) != required_asset_fields:
        raise ValueError("controlled asset manifest is incomplete")
    if (not isinstance(asset["id"], str) or not asset["id"]
            or not isinstance(asset["entityName"], str)
            or not asset["entityName"].startswith("OVERTE_E2E_ASSET_LOAD")
            or not isinstance(asset["route"], str)
            or not asset["route"].startswith("/assets/")
            or asset["encoding"] != "base64"
            or asset["contentType"] != "image/png"):
        raise ValueError("controlled asset identity or route is invalid")
    repository = ROOT.parents[2].resolve()
    source = asset_source(manifest)
    if repository not in source.parents or not source.is_file():
        raise ValueError("controlled asset source must be a repository file")
    payload = asset_payload(manifest)
    if (len(payload) != asset["bytes"]
            or hashlib.sha256(payload).hexdigest() != asset["sha256"]
            or png_dimensions(payload) != (asset["width"], asset["height"])):
        raise ValueError("controlled asset bytes do not match the manifest")
    sound = manifest.get("sound")
    if not isinstance(sound, dict) or set(sound) != {
            "path", "sha256", "mimeType", "sampleRate", "channels",
            "bitsPerSample", "durationSeconds", "frequencyHz"}:
        raise ValueError("fixture sound metadata is incomplete")
    sound_path = ROOT / sound["path"]
    sound_bytes = sound_path.read_bytes()
    if (sound["mimeType"] != "audio/wav" or sound["sampleRate"] != 8000
            or sound["channels"] != 1 or sound["bitsPerSample"] != 16
            or sound["durationSeconds"] != 8.0 or sound["frequencyHz"] != 440.0
            or hashlib.sha256(sound_bytes).hexdigest() != sound["sha256"]
            or len(sound_bytes) != 128044):
        raise ValueError("fixture sound does not match its deterministic PCM WAV contract")
    probe = PROBE.read_text(encoding="utf-8")
    if "Test.saveObject" not in probe or '"overte-probe.json"' not in probe:
        raise ValueError("controlled fixture probe does not satisfy the E2E contract")
    return manifest


class RequestTelemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: list[dict] = []

    def begin(self, asset: dict, request_id: str) -> dict:
        record = {
            "assetId": asset["id"], "requestId": request_id,
            "method": "GET", "path": asset["route"], "status": 200,
            "contentType": asset["contentType"], "contentLength": asset["bytes"],
            "sha256": asset["sha256"], "cacheControl": "no-store",
            "completed": False,
        }
        with self._lock:
            self._requests.append(record)
        return record

    def complete(self, record: dict) -> None:
        with self._lock:
            record["completed"] = True

    def summary(self, asset_id: str, request_id: str) -> dict:
        with self._lock:
            matches = [dict(item) for item in self._requests
                       if item["assetId"] == asset_id and item["requestId"] == request_id]
        completed = [item for item in matches if item["completed"]]
        return {
            "schemaVersion": 1, "assetId": asset_id, "requestId": request_id,
            "requests": len(matches), "completedRequests": len(completed),
            "bytesServed": sum(item["contentLength"] for item in completed),
            "latest": matches[-1] if matches else None,
            "latestCompleted": completed[-1] if completed else None,
        }


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: object, manifest: dict):
        super().__init__(address, handler)
        self.manifest = manifest
        self.telemetry = RequestTelemetry()
        self.fixture_state = FixtureState()


class FixtureHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlsplit(self.path)
        request_path = parsed.path
        if request_path == "/healthz":
            payload = b'{"ready":true,"schemaVersion":1}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path == "/overte_e2e_probe.js":
            payload = PROBE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        asset = self.server.manifest["asset"]
        if request_path == asset["route"]:
            query = parse_qs(parsed.query, keep_blank_values=True)
            request_ids = query.get("requestId", [])
            if (set(query) != {"requestId"} or len(request_ids) != 1
                    or not REQUEST_ID.fullmatch(request_ids[0])):
                self.send_error(400, "asset request requires one valid requestId")
                return
            payload = asset_payload(self.server.manifest)
            record = self.server.telemetry.begin(asset, request_ids[0])
            self.send_response(200)
            self.send_header("Content-Type", asset["contentType"])
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
            self.server.telemetry.complete(record)
            return
        if request_path == "/telemetry/asset-requests":
            query = parse_qs(parsed.query, keep_blank_values=True)
            asset_ids = query.get("assetId", [])
            request_ids = query.get("requestId", [])
            if (set(query) != {"assetId", "requestId"} or len(asset_ids) != 1
                    or len(request_ids) != 1 or asset_ids[0] != asset["id"]
                    or not REQUEST_ID.fullmatch(request_ids[0])):
                self.send_error(400, "telemetry query is invalid")
                return
            payload = (json.dumps(
                self.server.telemetry.summary(asset_ids[0], request_ids[0]),
                sort_keys=True,
            ) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path == "/sound-command.json":
            payload = (json.dumps(self.server.fixture_state.snapshot_command(), sort_keys=True)
                       + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path == "/sound-requests.json":
            payload = (json.dumps({
                "schemaVersion": 1,
                "requests": self.server.fixture_state.snapshot_requests(),
            }, sort_keys=True) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        sound_path = "/" + self.server.manifest["sound"]["path"]
        if request_path == sound_path:
            payload = (ROOT / self.server.manifest["sound"]["path"]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.server.fixture_state.record_request(
                self.command, parsed, 200, "audio/wav", len(payload))
            return
        if request_path == "/audio/invalid.wav":
            payload = b"OVERTE_E2E_INVALID_WAV\n"
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.server.fixture_state.record_request(
                self.command, parsed, 200, "audio/wav", len(payload))
            return
        if request_path.startswith("/audio/"):
            payload = b'{"error":"not found"}\n'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.server.fixture_state.record_request(
                self.command, parsed, 404, "application/json", len(payload))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlsplit(self.path).path != "/sound-command.json":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if not 0 < length <= 4096:
            self.send_error(400)
            return
        try:
            command = json.loads(self.rfile.read(length))
            command = self.server.fixture_state.set_command(command)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self.send_error(400, str(error))
            return
        payload = (json.dumps(command, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string: str, *arguments: object) -> None:
        print("fixture: " + format_string % arguments, file=sys.stderr)


class FixtureState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: list[dict] = []
        self.command = {"schemaVersion": 1, "commandId": "", "action": "idle",
                        "soundUrl": ""}

    def set_command(self, command: object) -> dict:
        if (not isinstance(command, dict)
                or set(command) != {"schemaVersion", "commandId", "action", "soundUrl"}
                or command.get("schemaVersion") != 1
                or command.get("action") not in {"play", "stop"}
                or not isinstance(command.get("commandId"), str)
                or not command["commandId"]
                or not isinstance(command.get("soundUrl"), str)):
            raise ValueError("invalid sound command")
        if command["action"] == "play" and urlsplit(command["soundUrl"]).scheme not in {
                "http", "https"}:
            raise ValueError("play command requires an HTTP(S) sound URL")
        with self._lock:
            self.command = dict(command)
            return dict(self.command)

    def record_request(self, method: str, target: object, status: int,
                       mime_type: str, bytes_sent: int) -> None:
        with self._lock:
            self._requests.append({
                "sequence": len(self._requests) + 1,
                "epochMs": int(time.time() * 1000),
                "method": method,
                "path": target.path,
                "query": parse_qs(target.query),
                "status": status,
                "mimeType": mime_type,
                "bytesSent": bytes_sent,
            })

    def snapshot_command(self) -> dict:
        with self._lock:
            return dict(self.command)

    def snapshot_requests(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._requests]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--public-host",
                        help="host/IP reachable by devices; defaults to --bind")
    parser.add_argument("--ready-file", type=Path,
                        help="atomically write connection metadata after binding")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be from 0 through 65535")
    return args


def main() -> int:
    args = arguments()
    manifest = validate_fixture()
    if args.check:
        print(f"PASS: controlled fixture contains {manifest['expectedEntityCount']} local entities")
        return 0
    handler = partial(FixtureHandler, directory=str(ROOT))
    server = FixtureServer((args.bind, args.port), handler, manifest)
    host = args.public_host or args.bind
    if host in {"0.0.0.0", "::"}:
        raise ValueError("--public-host is required when binding all interfaces")
    base_url = f"http://{host}:{server.server_address[1]}"
    asset = manifest["asset"]
    sound_path = manifest["sound"]["path"]
    ready = {"schemaVersion": 1, "baseUrl": base_url,
             "sceneUrl": controlled_scene_url(base_url, manifest),
             "probeScriptUrl": f"{base_url}/overte_e2e_probe.js",
             "asset": {
                 "id": asset["id"], "url": f"{base_url}{asset['route']}",
                 "telemetryUrl": f"{base_url}/telemetry/asset-requests",
                 "contentType": asset["contentType"],
                 "sha256": asset["sha256"], "bytes": asset["bytes"],
                 "width": asset["width"], "height": asset["height"],
                 "entityName": asset["entityName"],
             },
             "soundUrl": f"{base_url}/{sound_path}",
             "invalidSoundUrl": f"{base_url}/audio/invalid.wav",
             "soundCommandUrl": f"{base_url}/sound-command.json",
             "soundRequestsUrl": f"{base_url}/sound-requests.json",
             "sound": manifest["sound"]}
    if args.ready_file:
        args.ready_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.ready_file.with_suffix(args.ready_file.suffix + ".tmp")
        temporary.write_text(json.dumps(ready, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(args.ready_file)
    print(json.dumps(ready, sort_keys=True), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
