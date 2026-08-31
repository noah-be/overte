#!/usr/bin/env python3
"""Device-free checks for the controlled domain fixture controller."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "fixture" / "domain.py"

FAKE_DOMAIN = r'''#!/usr/bin/env python3
import http.server, os, signal
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/id":
            payload = b"11111111-2222-4333-8444-555555555555\n"
            self.send_response(200); self.send_header("Content-Length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
        else:
            self.send_error(404)
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(("127.0.0.1", int(os.environ["HIFI_DOMAIN_SERVER_HTTP_PORT"])), Handler)
def stop(*_):
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
server.serve_forever()
'''

FAKE_ASSIGNMENT = r'''#!/usr/bin/env python3
import json, os, pathlib, signal, sys, time, urllib.request
stopping = False
def stop(*_):
    global stopping
    stopping = True
signal.signal(signal.SIGTERM, stop)
if "--pool" in sys.argv and sys.argv[sys.argv.index("--pool") + 1] == "overte-e2e-domain":
    config = pathlib.Path(os.environ["XDG_CONFIG_HOME"]).parents[1] / "domain-config.json"
    value = json.loads(config.read_text())
    script = value["scripts"]["persistent_scripts"][0]["url"]
    request = urllib.request.Request(
        script.rsplit("/", 1)[0] + "/domain-ready", method="POST",
        data=b'{"schemaVersion":1,"markerCount":4}',
        headers={"Content-Type": "application/json"})
    for _ in range(50):
        try:
            urllib.request.urlopen(request, timeout=1).close(); break
        except OSError:
            time.sleep(0.02)
while not stopping:
    time.sleep(0.05)
'''


def free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


class DomainFixtureTest(unittest.TestCase):
    def test_domain_fixture_contract(self):
        result = subprocess.run(
            [sys.executable, str(CONTROLLER), "--check"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("assignment-owned markers", result.stdout)

    @unittest.skipIf(os.name == "nt", "executable-script fixture is POSIX-specific")
    def test_controller_owns_stack_and_publishes_exact_ready_contract(self):
        with tempfile.TemporaryDirectory(prefix="overte-domain-controller-test-") as temporary:
            root = Path(temporary)
            domain = root / "fake-domain.py"
            assignment = root / "fake-assignment.py"
            domain.write_text(FAKE_DOMAIN, encoding="utf-8")
            assignment.write_text(FAKE_ASSIGNMENT, encoding="utf-8")
            domain.chmod(0o700)
            assignment.chmod(0o700)
            ready = root / "ready.json"
            output = root / "output"
            process = subprocess.Popen([
                sys.executable, str(CONTROLLER),
                "--domain-server", str(domain),
                "--assignment-client", str(assignment),
                "--domain-port", str(free_port()),
                "--http-port", str(free_port()),
                "--script-port", "0",
                "--assignment-warmup-seconds", "0.1",
                "--output-dir", str(output),
                "--ready-file", str(ready),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                if not ready.exists():
                    stdout, _ = process.communicate(timeout=2)
                    self.fail("domain fixture did not become ready:\n" + stdout)
                metadata = json.loads(ready.read_text(encoding="utf-8"))
                self.assertEqual("11111111-2222-4333-8444-555555555555",
                                 metadata["domainId"])
                self.assertTrue(metadata["domainUrl"].startswith("hifi://127.0.0.1:"))
                self.assertEqual(4, metadata["expectedEntityCount"])
                self.assertEqual("OVERTE_E2E_PEER", metadata["peerDisplayName"])
                with urlopen(metadata["bootstrapScriptUrl"], timeout=2) as response:
                    script = response.read().decode("utf-8")
                self.assertIn('Entities.addEntity(properties, "domain")', script)
                with urlopen(metadata["peerScriptUrl"], timeout=2) as response:
                    peer_script = response.read().decode("utf-8")
                self.assertIn("Agent.isAvatar = true", peer_script)
                for action in ("offline", "online"):
                    request = Request(
                        metadata["controlUrl"], method="POST",
                        data=json.dumps({"schemaVersion": 1, "action": action}).encode(),
                        headers={
                            "Content-Type": "application/json",
                            "X-Overte-E2E-Token": metadata["controlToken"],
                        },
                    )
                    with urlopen(request, timeout=5) as response:
                        transition = json.loads(response.read())
                    self.assertEqual(action, transition["state"])
                    self.assertGreaterEqual(transition["generation"], 2)
                self.assertIsNone(process.poll())
            finally:
                process.terminate()
                stdout, _ = process.communicate(timeout=10)
            self.assertEqual(0, process.returncode, stdout)
            self.assertTrue((output / "domain-config.json").is_file())
            self.assertTrue((output / "domain-server.log").is_file())
            self.assertTrue((output / "assignment-client.log").is_file())


if __name__ == "__main__":
    unittest.main()
