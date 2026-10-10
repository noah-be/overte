#!/usr/bin/env python3
"""Generate the repository-owned deterministic PCM WAV E2E fixture."""

from __future__ import annotations

import argparse
import hashlib
import io
import math
from pathlib import Path
import struct
import wave


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "audio" / "overte-e2e-tone.wav"
SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
DURATION_SECONDS = 8.0
FREQUENCY_HZ = 440.0
AMPLITUDE = 0.2


def pcm_bytes(duration_seconds: float = DURATION_SECONDS) -> bytes:
    if (isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float))
            or not 0 < duration_seconds <= 120):
        raise ValueError("sound duration must be greater than zero and at most 120 seconds")
    frames = int(SAMPLE_RATE * duration_seconds)
    scale = int((2 ** 15 - 1) * AMPLITUDE)
    return b"".join(struct.pack(
        "<h", round(scale * math.sin(2.0 * math.pi * FREQUENCY_HZ * index / SAMPLE_RATE))
    ) for index in range(frames))


def wav_bytes(duration_seconds: float = DURATION_SECONDS) -> bytes:
    content = io.BytesIO()
    with wave.open(content, "wb") as output:
        output.setnchannels(CHANNELS)
        output.setsampwidth(SAMPLE_WIDTH_BYTES)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm_bytes(duration_seconds))
    return content.getvalue()


def write_fixture(path: Path = OUTPUT) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(CHANNELS)
        output.setsampwidth(SAMPLE_WIDTH_BYTES)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm_bytes())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        if not OUTPUT.is_file():
            raise ValueError(f"missing generated fixture: {OUTPUT}")
        expected = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
        temporary = OUTPUT.with_suffix(".check.wav")
        try:
            actual = write_fixture(temporary)
        finally:
            temporary.unlink(missing_ok=True)
        if actual != expected:
            raise ValueError("generated sound fixture is not reproducible")
        print(expected)
        return 0
    print(write_fixture())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, wave.Error) as error:
        print(f"error: {error}")
        raise SystemExit(2)
