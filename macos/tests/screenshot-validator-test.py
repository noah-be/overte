#!/usr/bin/env python3
"""Hermetic tests for the macOS screenshot pixel gate."""

from pathlib import Path
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "macos/tools/validate-screenshot.py"


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, pixel) -> None:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(pixel(x, y))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )


def run(image: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(image),
            "--min-width",
            "32",
            "--min-height",
            "32",
            *extra,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
    temporary = Path(directory)
    black = temporary / "black.png"
    write_png(black, 64, 64, lambda _x, _y: (0, 0, 0, 255))
    black_run = run(black)
    assert black_run.returncode == 1, black_run
    assert "non-black" in black_run.stdout

    fixture = temporary / "fixture.png"

    def fixture_pixel(x: int, y: int) -> tuple[int, int, int, int]:
        if x < 24:
            return (235, 48, 72, 255)
        if x >= 40:
            return (25, 210, 225, 255)
        return (30 + y * 2, 35 + y * 2, 50 + y * 2, 255)

    write_png(fixture, 64, 64, fixture_pixel)
    result = temporary / "result.json"
    fixture_run = run(
        fixture,
        "--require-red-pixels",
        "100",
        "--require-cyan-pixels",
        "100",
        "--require-red-left",
        "--require-cyan-right",
        "--result",
        str(result),
    )
    assert fixture_run.returncode == 0, fixture_run.stderr + fixture_run.stdout
    metrics = json.loads(result.read_text(encoding="utf-8"))
    assert metrics["passed"] is True
    assert metrics["red_pixels"] >= 100
    assert metrics["cyan_pixels"] >= 100
    assert metrics["red_centroid_x_ratio"] < 0.5
    assert metrics["cyan_centroid_x_ratio"] > 0.5
    assert metrics["opaque_ratio"] == 1.0
    assert result.stat().st_mode & 0o777 == 0o600

    malformed = temporary / "malformed.png"
    malformed.write_bytes(b"not a png")
    malformed_run = run(malformed)
    assert malformed_run.returncode == 1
    assert "signature" in malformed_run.stdout

    swapped = temporary / "swapped.png"
    write_png(
        swapped,
        64,
        64,
        lambda x, _y: (25, 210, 225, 255) if x < 32 else (235, 48, 72, 255),
    )
    swapped_run = run(
        swapped,
        "--require-red-pixels",
        "100",
        "--require-cyan-pixels",
        "100",
        "--require-red-left",
        "--require-cyan-right",
    )
    assert swapped_run.returncode == 1
    assert "left half" in swapped_run.stdout
    assert "right half" in swapped_run.stdout

    invalid_threshold = run(fixture, "--min-opaque-ratio", "1.1")
    assert invalid_threshold.returncode == 2
    assert "between zero and one" in invalid_threshold.stderr

print("macOS screenshot validator tests passed")
