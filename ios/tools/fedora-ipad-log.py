#!/usr/bin/env python3
"""Capture bounded, privacy-redacted Overte logs from one iPad on Fedora."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REVISION = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
BUNDLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{2,127}$")
DEVICE_ID = re.compile(r"(?<![A-Za-z0-9])(?:[0-9A-Fa-f]{8}-){1,4}[0-9A-Fa-f]{8,32}(?![A-Za-z0-9])")
UUID = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
IP_ADDRESS = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
PRIVATE_FIELD = re.compile(
    r"(?i)\b(user(?:name)?|owner|serial(?:number)?|udid|device(?:id|name)|apple[_ -]?id)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
HOME_PATH = re.compile(r"(?:(?:/Users|/home)/)[^/\s]+")
MODEL = re.compile(r"(?i)\b(?:iPad|iPhone)[0-9]+(?:,[0-9]+)?\b")
MAX_LINE_BYTES = 64 * 1024
MAX_LOG_BYTES = 2 * 1024 * 1024


class CaptureError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize(line: str, identifiers: list[str]) -> str:
    for identifier in identifiers:
        line = line.replace(identifier, "[REDACTED DEVICE ID]")
    line = UUID.sub("[REDACTED UUID]", line)
    line = DEVICE_ID.sub("[REDACTED DEVICE ID]", line)
    line = EMAIL.sub("[REDACTED EMAIL]", line)
    line = IP_ADDRESS.sub("[REDACTED IP]", line)
    line = PRIVATE_FIELD.sub(r"\1\2[REDACTED]", line)
    line = HOME_PATH.sub("/[REDACTED HOME]", line)
    return MODEL.sub("[REDACTED MODEL]", line)


def require_tools() -> tuple[str, str]:
    identity = shutil.which("idevice_id")
    syslog = shutil.which("idevicesyslog")
    if not identity or not syslog:
        raise CaptureError(
            "Fedora iPad tools are missing; install the package providing "
            "idevice_id and idevicesyslog"
        )
    return identity, syslog


def connected_devices(identity_tool: str) -> list[str]:
    result = subprocess.run(
        [identity_tool, "-l"], capture_output=True, text=True, timeout=15, check=False
    )
    if result.returncode != 0:
        raise CaptureError("iPad discovery failed")
    devices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if any(len(item) > 128 or not re.fullmatch(r"[A-Za-z0-9.-]+", item) for item in devices):
        raise CaptureError("iPad discovery returned an invalid identifier")
    return devices


def doctor() -> int:
    identity, _ = require_tools()
    count = len(connected_devices(identity))
    print(f"Fedora iPad log tools ready; connected device count: {count}")
    return 0


def capture(args: argparse.Namespace) -> int:
    identity_tool, syslog_tool = require_tools()
    devices = connected_devices(identity_tool)
    if len(devices) != 1:
        raise CaptureError("exactly one trusted iPad must be connected")
    if not REVISION.fullmatch(args.source_revision):
        raise CaptureError("source revision must be a 40-character lowercase SHA")
    if not DIGEST.fullmatch(args.ipa_sha256):
        raise CaptureError("IPA SHA-256 must be a 64-character lowercase digest")
    if not BUNDLE_ID.fullmatch(args.bundle_id):
        raise CaptureError("bundle identifier is invalid")
    if not 1 <= args.duration_seconds <= 3600:
        raise CaptureError("duration must be between 1 and 3600 seconds")

    output = args.output_dir
    if output.exists():
        raise CaptureError("output directory already exists")
    output.mkdir(parents=True, mode=0o700)
    log_path = output / "overte-ipad-syslog.txt"
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    retained: list[str] = ["OVERTE FEDORA IPAD CAPTURE START\n"]
    retained_bytes = len(retained[0].encode())
    matched = 0

    process = subprocess.Popen(
        [syslog_tool], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", start_new_session=True
    )
    deadline = time.monotonic() + args.duration_seconds
    selector = selectors.DefaultSelector()
    try:
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            ready = selector.select(timeout=min(0.25, max(0.0, deadline - time.monotonic())))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                continue
            if args.bundle_id not in line and "overte" not in line.lower():
                continue
            clean = sanitize(line, devices)
            encoded = clean.encode("utf-8")
            if retained_bytes + len(encoded) > MAX_LOG_BYTES:
                break
            retained.append(clean)
            retained_bytes += len(encoded)
            matched += 1
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

    retained.append("OVERTE FEDORA IPAD CAPTURE END\n")
    log_path.write_text("".join(retained), encoding="utf-8")
    log_path.chmod(0o600)
    manifest = {
        "schemaVersion": 1,
        "formFactor": "ipad",
        "sourceRevision": args.source_revision,
        "ipaSha256": args.ipa_sha256,
        "bundleIdentifier": args.bundle_id,
        "capturedAtUtc": started,
        "durationSeconds": args.duration_seconds,
        "matchedLineCount": matched,
        "log": log_path.name,
        "logSha256": sha256_file(log_path),
        "privacy": {
            "containsRawDeviceIdentifier": False,
            "containsDeviceModel": False,
            "containsUserInformation": False,
        },
    }
    manifest_path = output / "capture.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    print(f"Captured {matched} privacy-filtered Overte log lines")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor")
    capture_parser = subcommands.add_parser("capture")
    capture_parser.add_argument("--output-dir", required=True, type=Path)
    capture_parser.add_argument("--bundle-id", required=True)
    capture_parser.add_argument("--source-revision", required=True)
    capture_parser.add_argument("--ipa-sha256", required=True)
    capture_parser.add_argument("--duration-seconds", type=int, default=300)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return doctor() if args.command == "doctor" else capture(args)
    except (CaptureError, OSError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
