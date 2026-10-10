"""Versioned voice challenge and PCM detector; Python standard library only."""

from __future__ import annotations

import array
import bisect
import hashlib
import math
from pathlib import Path
import re
import sys
import wave

VERSION = 1
RATE = 24000
FREQUENCIES = (500, 650, 800, 950, 1100, 1250, 1400, 1550)
SYMBOLS = 12
LEAD = 0.5
TONE = 0.24
GAP = 0.08
CELL = TONE + GAP
DURATION = LEAD * 2 + SYMBOLS * CELL
WINDOW = 0.04
HOP = 0.02


def sequence(challenge: str) -> list[int]:
    if not isinstance(challenge, str) or not re.fullmatch(r"[0-9a-f]{32}", challenge):
        raise ValueError("challenge must be 32 lowercase hexadecimal characters")
    digest = hashlib.sha256(("overte-voice-v1:" + challenge).encode("ascii")).digest()
    result = [digest[0] % len(FREQUENCIES)]
    for value in digest[1:SYMBOLS]:
        result.append((result[-1] + 1 + value % (len(FREQUENCIES) - 1)) % len(FREQUENCIES))
    return result


def samples(challenge: str, rate: int = RATE, amplitude: float = 0.15) -> array.array:
    if rate not in (8000, 16000, 24000, 44100, 48000):
        raise ValueError("unsupported challenge sample rate")
    if not 0 < amplitude <= 0.25:
        raise ValueError("challenge amplitude must be in (0, 0.25]")
    output = array.array("h", [0]) * round(DURATION * rate)
    for index, symbol in enumerate(sequence(challenge)):
        start = round((LEAD + index * CELL) * rate)
        length = round(TONE * rate)
        ramp = max(1, round(0.008 * rate))
        for frame in range(length):
            envelope = min(1.0, frame / ramp, (length - frame - 1) / ramp)
            output[start + frame] = round(amplitude * 32767 * envelope
                                          * math.sin(2 * math.pi * FREQUENCIES[symbol] * frame / rate))
    return output


def write_wav(path: Path, challenge: str) -> None:
    pcm = samples(challenge)
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(pcm.tobytes())


def read_wav(path: Path) -> tuple[int, list[array.array]]:
    # Bound analysis input to one short lab capture (not an arbitrary media file).
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("WAV exceeds the 32 MiB capture limit")
    with wave.open(str(path), "rb") as source:
        rate, channels = source.getframerate(), source.getnchannels()
        if source.getsampwidth() != 2 or channels not in (1, 2) or not 8000 <= rate <= 48000:
            raise ValueError("expected mono/stereo 16-bit PCM WAV at 8-48 kHz")
        count = source.getnframes()
        if not 0 < count <= rate * 60:
            raise ValueError("capture must contain between 0 and 60 seconds")
        data = source.readframes(count)
        if len(data) != count * channels * 2:
            raise ValueError("WAV payload is truncated")
    pcm = array.array("h")
    pcm.frombytes(data)
    if sys.byteorder != "little":
        pcm.byteswap()
    return rate, [pcm[channel::channels] for channel in range(channels)]


def features(pcm: array.array, rate: int) -> list[tuple[float, int | None]]:
    # Keep at least 8 kHz; evaluate at the actual decimated rate, also for 44.1 kHz.
    step = max(1, rate // 8000)
    data = pcm[::step]
    effective_rate = rate / step
    size, hop = round(WINDOW * effective_rate), round(HOP * effective_rate)
    coefficients = [2 * math.cos(2 * math.pi * frequency / effective_rate)
                    for frequency in FREQUENCIES]
    result = []
    for start in range(0, len(data) - size + 1, hop):
        block = data[start:start + size]
        mean = sum(block) / size
        centered = [sample - mean for sample in block]
        energy = sum(sample * sample for sample in centered)
        label = None
        if energy / size >= (32767 * 10 ** (-50 / 20)) ** 2:
            powers = []
            for coefficient in coefficients:
                previous = previous2 = 0.0
                for value in centered:
                    current = value + coefficient * previous - previous2
                    previous2, previous = previous, current
                powers.append(previous * previous + previous2 * previous2
                              - coefficient * previous * previous2)
            best = max(range(len(powers)), key=powers.__getitem__)
            if 2 * powers[best] / (size * energy) >= 0.55:
                label = best
        result.append(((start + size / 2) / effective_rate, label))
    return result


def analyze(path: Path, challenge: str, expect: str = "present") -> dict:
    expected = sequence(challenge)
    if expect not in ("present", "absent"):
        raise ValueError("expect must be present or absent")
    rate, channels = read_wav(path)
    duration = len(channels[0]) / rate
    best_coverage = [0.0] * SYMBOLS
    best_offset = None
    best_channel = None
    best_score = 0.0
    for channel_index, pcm in enumerate(channels):
        observed = features(pcm, rate)
        # Try all possible first-tone offsets, preserving symbol order and timing.
        # Never combine channels: inverted stereo must not cancel a real signal.
        by_frame = [label for _, label in observed]
        times = [timestamp for timestamp, _ in observed]
        for frame in range(len(observed)):
            offset = observed[frame][0] - WINDOW / 2
            if offset + (SYMBOLS - 1) * CELL + TONE > duration:
                break
            coverage = []
            for symbol_index, symbol in enumerate(expected):
                low = offset + symbol_index * CELL + WINDOW
                high = offset + symbol_index * CELL + TONE - WINDOW
                lo = bisect.bisect_left(times, low - 1e-6)
                hi = bisect.bisect_right(times, high + 1e-6)
                labels = by_frame[lo:hi]
                coverage.append(sum(value == symbol for value in labels) / max(1, len(labels)))
            score = min(coverage) * 0.5 + sum(coverage) / SYMBOLS * 0.5
            if score > best_score:
                best_score, best_coverage = score, coverage
                best_offset, best_channel = offset, channel_index
    energy = sum(value * value for channel in channels for value in channel)
    count = sum(len(channel) for channel in channels)
    rms = math.sqrt(energy / count) / 32768
    rms_db = 20 * math.log10(max(rms, 1e-9))
    clipping = sum(abs(value) >= 32760 for channel in channels for value in channel) / count
    found = min(best_coverage) >= 0.65 and sum(best_coverage) / SYMBOLS >= 0.85
    complete = duration >= DURATION
    passed = complete and ((found and clipping < 0.01) if expect == "present"
                           else (not found and rms_db < -55))
    return {
        "schemaVersion": VERSION, "challenge": challenge, "expected": expect,
        "passed": passed, "patternDetected": found, "completeCapture": complete,
        "durationSeconds": round(duration, 4), "sampleRate": rate,
        "channelCount": len(channels), "matchedChannel": best_channel,
        "firstToneOffsetSeconds": None if best_offset is None else round(best_offset, 4),
        "symbolCoverage": [round(value, 4) for value in best_coverage],
        "rmsDbFS": round(rms_db, 2), "clippingFraction": round(clipping, 6),
        "proof": "PCM pattern detection; no physical microphone or loudspeaker claim",
    }
