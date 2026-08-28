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
from urllib.request import urlopen


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
import signal, sys, time
arguments = sys.argv[1:]
assignment_type = arguments[arguments.index("-t") + 1] if "-t" in arguments else ""
core = assignment_type in {"0", "1", "3", "4", "5", "6"} and "--pool" not in arguments
agent = ("-t" in arguments and arguments[arguments.index("-t") + 1] == "2"
         and "--pool" in arguments
         and arguments[arguments.index("--pool") + 1] == "overte-e2e-domain")
if not (core or agent):
    raise SystemExit(12)
if agent:
    print("OVERTE_E2E_DOMAIN_FIXTURE_READY markers=4", flush=True)
stopping = False
def stop(*_):
    global stopping
    stopping = True
signal.signal(signal.SIGTERM, stop)
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
                with urlopen(metadata["bootstrapScriptUrl"], timeout=2) as response:
                    script = response.read().decode("utf-8")
                self.assertIn('Entities.addEntity(properties, "domain")', script)
                self.assertIn('Script.resolvePath("domain-ready")', script)
                self.assertIsNone(process.poll())
            finally:
                process.terminate()
                stdout, _ = process.communicate(timeout=10)
            self.assertEqual(0, process.returncode, stdout)
            self.assertTrue((output / "domain-config.json").is_file())
            self.assertTrue((output / "domain-server.log").is_file())
            self.assertTrue((output / "assignment-client.log").is_file())
            self.assertTrue((output / "assignment-agent.log").is_file())


if __name__ == "__main__":
    unittest.main()
