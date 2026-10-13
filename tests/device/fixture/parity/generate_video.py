#!/usr/bin/env python3
"""Generate the repository-owned six-second web compositing reference."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

WIDTH, HEIGHT, FPS, SECONDS = 192, 108, 12, 6
DIGITS = ("111101101101111", "010110010010111", "111001111100111",
          "111001111001111", "101101111001001", "111100111001111",
          "111100111101111", "111001001001001", "111101111101111",
          "111101111001111")


def frame(number):
    color = ((200, 32, 32), (32, 180, 32), (32, 32, 200))[number // (FPS * 2)]
    image = bytearray(bytes(color) * WIDTH * HEIGHT)
    def box(x, y, width, height, rgb):
        for row in range(y, y + height):
            offset = (row * WIDTH + x) * 3
            image[offset:offset + width * 3] = bytes(rgb) * width
    # Actual encoded pixels, not a DOM animation over a frozen video frame.
    box(8 + (number * 2) % 160, 70, 16, 16, (255, 255, 255))
    for position, digit in enumerate(f"{number:03d}"):
        for cell, enabled in enumerate(DIGITS[int(digit)]):
            if enabled == "1":
                box(12 + position * 24 + cell % 3 * 5, 12 + cell // 3 * 5, 5, 5, (255, 255, 255))
    return bytes(image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("reference.mp4"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
               "-framerate", str(FPS), "-i", "pipe:0", "-f", "lavfi", "-i",
               "sine=frequency=440:sample_rate=22050:duration=6", "-t", str(SECONDS),
               "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact",
               "-flags:a", "+bitexact", "-c:v", "libx264", "-threads:v", "1",
               "-preset", "medium", "-crf", "23", "-profile:v", "baseline", "-level:v", "3.0",
               "-pix_fmt", "yuv420p", "-g", "12", "-c:a", "aac", "-b:a", "48k", "-ac", "1",
               "-movflags", "+faststart", str(args.output)]
    subprocess.run(command, input=b"".join(frame(i) for i in range(FPS * SECONDS)), check=True)
    payload = args.output.read_bytes()
    manifest = {"schemaVersion": 1, "file": args.output.name, "contentType": "video/mp4",
                "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                "width": WIDTH, "height": HEIGHT, "fps": FPS, "frames": FPS * SECONDS,
                "durationSeconds": SECONDS, "videoCodec": "h264-baseline", "audioCodec": "aac",
                "sampleRate": 22050, "channels": 1, "frequencyHz": 440,
                "visual": "red/green/blue at 0/2/4 seconds, encoded frame counter 000..071 and moving white square"}
    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
