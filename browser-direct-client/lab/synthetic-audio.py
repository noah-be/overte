#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Send or record bounded synthetic PCM through this lab's private Pulse servers."""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from manage import ROOT


def pulse(participant: str) -> str:
    return f"unix:{ROOT}/runtime/{'b.sock' if participant == 'browser' else 'n.sock'}"


def metadata(path: Path, participant: str, operation: str) -> dict:
    return {"operation": operation, "participant": participant,
            "syntheticOnly": True, "physicalMicrophoneTested": False,
            "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def tone(args: argparse.Namespace) -> None:
    rate = 48000
    samples = array.array("h", (round(8191 * math.sin(2 * math.pi * args.frequency * n / rate))
                                 for n in range(round(args.seconds * rate))))
    if sys.byteorder != "little":
        samples.byteswap()
    directory = ROOT / "audio-proof"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{args.participant}-tone-{time.time_ns()}.s16le"
    path.write_bytes(samples.tobytes())
    subprocess.run(["paplay", "--server", pulse(args.participant), "--device",
                    f"{args.participant}_input", "--raw", "--format=s16le", "--rate=48000",
                    "--channels=1", "--latency-msec=20", str(path)], check=True, timeout=args.seconds + 5)
    print(json.dumps({**metadata(path, args.participant, "synthetic-input"),
                      "frequency": args.frequency, "seconds": args.seconds, "rate": rate}))


def capture(args: argparse.Namespace) -> None:
    directory = ROOT / "audio-proof"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{args.participant}-output-{time.time_ns()}.s16le"
    with path.open("wb") as output:
        process = subprocess.Popen(["parecord", "--server", pulse(args.participant), "--device",
                                    f"{args.participant}_output.monitor", "--raw", "--format=s16le",
                                    "--rate=48000", "--channels=2", "--latency-msec=20"], stdout=output,
                                   stderr=subprocess.PIPE)
        try:
            time.sleep(args.seconds)
        finally:
            process.terminate()
            try:
                _, errors = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                _, errors = process.communicate(timeout=2)
    if process.returncode not in (0, -15):
        raise RuntimeError(f"Private Pulse recording failed with code {process.returncode}")
    samples = array.array("h")
    samples.frombytes(path.read_bytes())
    if sys.byteorder != "little":
        samples.byteswap()
    mono = [((samples[n] + samples[n + 1]) / (2 * 32768)) for n in range(0, len(samples) - 1, 2)]
    rms = math.sqrt(sum(value * value for value in mono) / len(mono)) if mono else 0
    energies = {}
    for frequency in (523.25, 659.25, args.frequency):
        cosine = math.cos(2 * math.pi * frequency / 48000)
        sine = math.sin(2 * math.pi * frequency / 48000)
        phase_real, phase_imag = 1.0, 0.0
        real, imag = 0.0, 0.0
        for value in mono:
            real += value * phase_real
            imag += value * phase_imag
            phase_real, phase_imag = (phase_real * cosine - phase_imag * sine,
                                      phase_real * sine + phase_imag * cosine)
        energies[str(frequency)] = 2 * math.hypot(real, imag) / len(mono) if mono else 0
    result = {**metadata(path, args.participant, "actual-output-monitor"),
              "requestedSeconds": args.seconds, "capturedFrames": len(mono), "rate": 48000,
              "rms": rms, "frequencyAmplitudes": energies,
              "note": "Output monitor evidence alone does not identify a remote sender."}
    path.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("tone", "capture"))
    parser.add_argument("--participant", choices=("browser", "native"), required=True)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--frequency", type=float, default=523.25)
    args = parser.parse_args()
    if not (0 < args.seconds <= 30 and 20 <= args.frequency <= 12000):
        parser.error("use 0–30 seconds and an audible 20–12000 Hz tone")
    if args.operation == "tone":
        tone(args)
    else:
        capture(args)


if __name__ == "__main__":
    main()
