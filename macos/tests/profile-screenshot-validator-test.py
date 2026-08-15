#!/usr/bin/env python3
"""Hermetic visual contract for macOS profile-matrix acceptance images."""

from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "macos/tools/validate-screenshot.py"
RUNNER = ROOT / "macos/ci/performance-matrix.sh"


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, pixel) -> None:
    width = height = 64
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


def validate(image: Path, *, semantic: bool) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        str(image),
        "--min-width",
        "32",
        "--min-height",
        "32",
    ]
    if semantic:
        command.extend([
            "--require-red-pixels",
            "128",
            "--require-cyan-pixels",
            "128",
            "--require-red-left",
            "--require-cyan-right",
        ])
    return subprocess.run(command, text=True, capture_output=True, check=False)


runner = RUNNER.read_text(encoding="utf-8")
for contract in (
    'local warmup_snapshot="$run_dir/macos-profile-warmup.png"',
    'local snapshot="$run_dir/macos-profile.png"',
    'grep -Fq "OVERTE_MACOS_PROFILE warmup_cooldown_ms="',
    "--require-red-pixels 128 --require-cyan-pixels 128",
    "--require-red-left --require-cyan-right",
):
    assert contract in runner, f"profile matrix runner is missing visual contract: {contract}"

with tempfile.TemporaryDirectory() as directory:
    temporary = Path(directory)
    sky = temporary / "sky-only.png"

    def sky_pixel(x: int, y: int) -> tuple[int, int, int, int]:
        if 27 <= y <= 36:
            return (0, 8 + x // 3, 22 + x // 2, 255)
        return (0, 0, 0, 255)

    write_png(sky, sky_pixel)
    generic = validate(sky, semantic=False)
    assert generic.returncode == 0, generic.stdout + generic.stderr
    semantic = validate(sky, semantic=True)
    assert semantic.returncode == 1, semantic.stdout + semantic.stderr
    assert "required red fixture pixels" in semantic.stdout
    assert "required cyan fixture pixels" in semantic.stdout

    fixture = temporary / "fixture.png"

    def fixture_pixel(x: int, y: int) -> tuple[int, int, int, int]:
        if x < 24:
            return (235, 48, 72, 255)
        if x >= 40:
            return (25, 210, 225, 255)
        return (30 + y * 2, 35 + y * 2, 50 + y * 2, 255)

    write_png(fixture, fixture_pixel)
    accepted = validate(fixture, semantic=True)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr

print("macOS profile screenshot validator contract valid")
