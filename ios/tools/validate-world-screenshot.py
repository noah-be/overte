#!/usr/bin/env python3
"""Validate that a retained iOS world screenshot is a real, non-blank PNG."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import zlib


MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 12 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ScreenshotError(ValueError):
    pass


def paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distances = (abs(estimate - left), abs(estimate - above), abs(estimate - upper_left))
    return (left, above, upper_left)[distances.index(min(distances))]


def parse_png(path: Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    size = path.stat().st_size
    if size < 100 or size > MAX_FILE_BYTES:
        raise ScreenshotError("screenshot size is outside the accepted boundary")
    payload = path.read_bytes()
    if not payload.startswith(PNG_SIGNATURE):
        raise ScreenshotError("screenshot is not a PNG")

    offset = len(PNG_SIGNATURE)
    width = height = color_type = bit_depth = None
    compressed = bytearray()
    saw_data = False
    saw_end = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ScreenshotError("truncated PNG chunk")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(payload):
            raise ScreenshotError("PNG chunk exceeds the file")
        body = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : end])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != expected_crc:
            raise ScreenshotError("PNG chunk CRC mismatch")
        if kind == b"IHDR":
            if width is not None or offset != len(PNG_SIGNATURE) or length != 13:
                raise ScreenshotError("invalid PNG header")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", body
            )
            if compression or filtering or interlace:
                raise ScreenshotError("unsupported PNG encoding")
        elif kind == b"IDAT":
            if width is None:
                raise ScreenshotError("PNG pixel data precedes its header")
            saw_data = True
            compressed.extend(body)
            if len(compressed) > MAX_FILE_BYTES:
                raise ScreenshotError("compressed screenshot payload is too large")
        elif kind == b"IEND":
            if length != 0:
                raise ScreenshotError("invalid PNG end marker")
            saw_end = True
            offset = end
            break
        elif kind[0] & 0x20 == 0:
            raise ScreenshotError("screenshot contains an unsupported critical PNG chunk")
        offset = end

    if not saw_end or offset != len(payload) or width is None or height is None or not saw_data:
        raise ScreenshotError("PNG is incomplete")
    if width < 320 or height < 320 or width * height > MAX_PIXELS:
        raise ScreenshotError("screenshot dimensions are outside the accepted boundary")
    if bit_depth != 8 or color_type not in (2, 6):
        raise ScreenshotError("screenshot must use 8-bit RGB or RGBA pixels")

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    expected = (stride + 1) * height
    try:
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(bytes(compressed), expected + 1)
        if decompressor.unconsumed_tail or len(raw) > expected:
            raise ScreenshotError("screenshot pixel stream exceeds the declared dimensions")
        raw += decompressor.flush(expected + 1 - len(raw))
    except zlib.error as error:
        raise ScreenshotError("screenshot pixel stream is invalid") from error
    if (
        len(raw) != expected
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
    ):
        raise ScreenshotError("screenshot pixel stream has the wrong size")

    rows: list[bytearray] = []
    cursor = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_kind = raw[cursor]
        encoded = raw[cursor + 1 : cursor + 1 + stride]
        cursor += stride + 1
        decoded = bytearray(stride)
        for index, value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_kind == 0:
                result = value
            elif filter_kind == 1:
                result = value + left
            elif filter_kind == 2:
                result = value + above
            elif filter_kind == 3:
                result = value + ((left + above) // 2)
            elif filter_kind == 4:
                result = value + paeth(left, above, upper_left)
            else:
                raise ScreenshotError("screenshot uses an unknown PNG filter")
            decoded[index] = result & 0xFF
        rows.append(decoded)
        previous = decoded

    pixels: list[tuple[int, int, int]] = []
    sample_step = max(1, int(math.sqrt((width * height) / 250_000)))
    for y in range(0, height, sample_step):
        row = rows[y]
        for x in range(0, width, sample_step):
            start = x * channels
            if channels == 4 and row[start + 3] < 16:
                continue
            pixels.append((row[start], row[start + 1], row[start + 2]))
    if len(pixels) < 10_000:
        raise ScreenshotError("screenshot contains too few visible pixels")
    return width, height, pixels


def validate(path: Path, scenario: str, destination: str) -> dict[str, object]:
    width, height, pixels = parse_png(path)
    buckets = {(red // 16, green // 16, blue // 16) for red, green, blue in pixels}
    luminance = [(54 * red + 183 * green + 19 * blue) / 256 for red, green, blue in pixels]
    average = sum(luminance) / len(luminance)
    deviation = math.sqrt(sum((value - average) ** 2 for value in luminance) / len(luminance))
    # A textured skybox is valid presentation evidence, but it is not proof
    # that world geometry is visible. Require a small amount of bright neutral
    # or non-blue content so a star field alone cannot satisfy the world test.
    world_detail = sum(
        red > blue + 10
        or green > blue + 10
        or (max(red, green, blue) - min(red, green, blue) < 15 and max(red, green, blue) > 80)
        for red, green, blue in pixels
    )
    world_detail_fraction = world_detail / len(pixels)
    if len(buckets) < 24 or deviation < 6.0 or world_detail_fraction < 0.005:
        raise ScreenshotError("screenshot is blank or lacks visible world detail")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "schemaVersion": 1,
        "accepted": True,
        "scenario": scenario,
        "destination": destination,
        "file": path.name,
        "sha256": digest,
        "width": width,
        "height": height,
        "sampledVisiblePixels": len(pixels),
        "quantizedColorBuckets": len(buckets),
        "luminanceStandardDeviation": round(deviation, 3),
        "worldDetailFraction": round(world_detail_fraction, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--scenario", choices=("serverless", "online"), required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate(args.screenshot, args.scenario, args.destination)
    except (OSError, ScreenshotError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
