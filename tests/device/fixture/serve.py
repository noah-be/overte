#!/usr/bin/env python3
"""Serve and validate the deterministic Overte physical-device E2E fixture."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parent
PROBE = ROOT.parent / "probe" / "overte_e2e_probe.js"
URL = re.compile(r"(?:https?|ftp)://", re.IGNORECASE)


def controlled_scene_url(base_url: str, manifest: dict) -> str:
    return f"{base_url}/{manifest['scene']}?{urlencode({'location': manifest['spawnPath']})}"


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
    probe = PROBE.read_text(encoding="utf-8")
    if "Test.saveObject" not in probe or '"overte-probe.json"' not in probe:
        raise ValueError("controlled fixture probe does not satisfy the E2E contract")
    return manifest


class FixtureHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        request_path = self.path.split("?", 1)[0]
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
        super().do_GET()

    def log_message(self, format_string: str, *arguments: object) -> None:
        print("fixture: " + format_string % arguments, file=sys.stderr)


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
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    host = args.public_host or args.bind
    if host in {"0.0.0.0", "::"}:
        raise ValueError("--public-host is required when binding all interfaces")
    base_url = f"http://{host}:{server.server_address[1]}"
    ready = {"schemaVersion": 1, "baseUrl": base_url,
             "sceneUrl": controlled_scene_url(base_url, manifest),
             "probeScriptUrl": f"{base_url}/overte_e2e_probe.js"}
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
