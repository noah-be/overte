#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Serve this lab's immutable actual-asset mirror over isolated HTTPS with CORS."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.server
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import unquote, urlsplit

from manage import REPO, ROOT, owns_process, process_identity

DIRECTORY = ROOT / "https-assets"
STATE = ROOT / "runtime/https-fixtures.json"
PORT = 46119
ORIGIN = "http://127.0.0.1:46106"
AUDIT = ROOT / "runtime/https-fixture-requests.jsonl"
AUDIT_LOCK = threading.Lock()
ASSET_HASHES = {}


class Assets(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Type")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        if "\x00" in path or "\\" in path:
            self.send_error(400)
            return None
        target = (DIRECTORY / path.lstrip("/")).resolve()
        if not target.is_relative_to(DIRECTORY.resolve()) or not target.is_file():
            self.send_error(404)
            return None
        stream = super().send_head()
        if stream is not None:
            with AUDIT_LOCK:
                if not AUDIT.exists() or AUDIT.stat().st_size < 2 * 1024 * 1024:
                    identity = (str(target), target.stat().st_mtime_ns, target.stat().st_size)
                    digest = ASSET_HASHES.get(identity)
                    if digest is None:
                        digest = hashlib.sha256(target.read_bytes()).hexdigest()
                        ASSET_HASHES[identity] = digest
                    agent = self.headers.get("User-Agent", "")
                    record = {"unixTime": time.time(), "serverPID": os.getpid(),
                              "method": self.command,
                              "relativePath": str(target.relative_to(DIRECTORY.resolve())),
                              "bytes": target.stat().st_size, "servedSHA256": digest,
                              "clientClass": "Chrome" if "Chrome/" in agent else
                                  "Qt" if "Qt/" in agent or "Overte" in agent else "other"}
                    with AUDIT.open("a") as audit:
                        audit.write(json.dumps(record) + "\n")
                    AUDIT.chmod(0o600)
        return stream

    def log_message(self, *_arguments) -> None:
        # Asset URLs and request headers are not printed to shared output.
        pass


def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def write_state(state: dict) -> None:
    temporary = STATE.with_suffix(".pending")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(STATE)


def certificate() -> tuple[Path, Path]:
    directory = ROOT / "runtime/fixture-tls"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    key, cert = directory / "key.pem", directory / "cert.pem"
    if not key.is_file() or not cert.is_file():
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
                        "-days", "2", "-subj", "/CN=Overte direct browser local fixture",
                        "-addext", "subjectAltName=IP:127.0.0.1,IP:127.0.0.3",
                        "-keyout", str(key), "-out", str(cert)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        key.chmod(0o600)
        cert.chmod(0o600)
    return key, cert


def rotate_tls() -> None:
    state = read_state()
    if state and owns_process(state):
        raise RuntimeError("Stop the owned fixture after browser tests finish before rotating TLS")
    current = ROOT / "runtime/fixture-tls"
    if current.is_symlink():
        current.unlink()
    elif current.is_dir():
        archived = ROOT / f"runtime/fixture-tls-retained-{time.time_ns()}"
        current.rename(archived)
    versioned = ROOT / f"runtime/fixture-tls-rsa2048-{time.time_ns()}"
    versioned.mkdir(mode=0o700)
    current.symlink_to(versioned, target_is_directory=True)
    _key, cert = certificate()
    print(json.dumps({"rotated": True, "algorithm": "RSA-2048/SHA-256",
                      "certificateSHA256": hashlib.sha256(cert.read_bytes()).hexdigest(),
                      "certificateDirectory": str(versioned),
                      "hostTrustChanged": False, "verificationDisabled": False}))


def serve() -> None:
    key, cert = certificate()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    def handler(*args, **kwargs):
        return Assets(*args, directory=str(DIRECTORY), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


def start() -> None:
    state = read_state()
    if state and owns_process(state):
        raise RuntimeError("The owned HTTPS fixture server is already running")
    if not DIRECTORY.is_dir() or not any(path.is_file() for path in DIRECTORY.rglob("*")):
        raise RuntimeError("Prepare the verified actual-asset mirror before starting HTTPS fixtures")
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", PORT))
        probe.listen(1)
    certificate()
    with (ROOT / "logs/https-fixtures.log").open("w") as output:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve"],
                                   cwd=REPO, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    identity = process_identity(process.pid)
    if identity is None:
        raise RuntimeError("Owned HTTPS fixture exited before registration")
    write_state(identity)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Owned HTTPS fixture exited; inspect its private log")
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                print(json.dumps({"started": True, "https": f"https://127.0.0.1:{PORT}",
                                  "corsOrigin": ORIGIN, "selfSignedLocalTestCertificate": True,
                                  "protocolProxy": False}))
                return
        except OSError:
            time.sleep(0.05)
    stop()
    raise RuntimeError("Owned HTTPS fixture did not become ready")


def stop() -> None:
    state = read_state()
    if state and owns_process(state):
        os.killpg(state["group"], signal.SIGTERM)
        deadline = time.monotonic() + 3
        while owns_process(state) and time.monotonic() < deadline:
            time.sleep(0.1)
        if owns_process(state):
            os.killpg(state["group"], signal.SIGKILL)
            time.sleep(0.2)
        if owns_process(state):
            raise RuntimeError("Owned HTTPS fixture failed cleanup")
    write_state({})
    print(json.dumps({"stopped": True, "remainingOwnedProcesses": 0}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("start", "status", "stop", "serve", "rotate-tls"))
    args = parser.parse_args()
    (ROOT / "runtime").mkdir(mode=0o700, parents=True, exist_ok=True)
    (ROOT / "logs").mkdir(mode=0o700, exist_ok=True)
    if args.operation == "serve":
        serve()
        return
    with (ROOT / "runtime/https-fixtures.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.operation == "start":
            start()
        elif args.operation == "stop":
            stop()
        elif args.operation == "rotate-tls":
            rotate_tls()
        else:
            state = read_state()
            print(json.dumps({"alive": bool(state) and owns_process(state), "port": PORT}))


if __name__ == "__main__":
    main()
