"""Serve one checked media reference with native-browser byte range support."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import re


def load_reference(root: Path):
    metadata = json.loads((root / "parity/reference.json").read_text())
    payload = (root / "parity/reference.mp4").read_bytes()
    if (metadata.get("schemaVersion") != 1 or metadata.get("file") != "reference.mp4"
            or metadata.get("contentType") != "video/mp4"
            or metadata.get("bytes") != len(payload)
            or metadata.get("sha256") != hashlib.sha256(payload).hexdigest()
            or payload[4:8] != b"ftyp"):
        raise ValueError("web parity media does not match its manifest")
    return metadata, payload


def byte_range(value: str, size: int):
    if len(value) > 128:
        raise ValueError("range too long")
    match = re.fullmatch(r"bytes=([0-9]{0,16})-([0-9]{0,16})", value)
    if not match or not any(match.groups()):
        raise ValueError("single byte range required")
    start, end = match.groups()
    if not start:
        length = int(end)
        if length <= 0:
            raise ValueError("empty suffix")
        return max(0, size - length), size - 1
    start = int(start)
    end = min(int(end), size - 1) if end else size - 1
    if start >= size or start > end:
        raise ValueError("range outside reference")
    return start, end


def send_reference(handler, *, head=False):
    payload = handler.server.parity_payload
    etag = '"' + handler.server.parity_manifest["sha256"] + '"'
    value = handler.headers.get("Range")
    # HEAD describes the full representation. An If-Range mismatch requests it
    # too; partial bytes must never be presented as a different representation.
    use_range = value is not None and not head and handler.headers.get("If-Range", etag) == etag
    if use_range:
        try:
            start, end = byte_range(value, len(payload))
        except ValueError:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{len(payload)}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
    else:
        start, end = 0, len(payload) - 1
    handler.send_response(206 if use_range else 200)
    handler.send_header("Content-Type", "video/mp4")
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("ETag", etag)
    handler.send_header("Content-Length", str(end - start + 1))
    if use_range:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
    handler.end_headers()
    if not head:
        handler.wfile.write(payload[start:end + 1])
