#!/usr/bin/env python3
"""Validate macOS smoke screenshots without third-party image packages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


class ScreenshotError(RuntimeError):
    pass


def _paeth(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    distance_left = abs(prediction - left)
    distance_above = abs(prediction - above)
    distance_upper_left = abs(prediction - upper_left)
    if distance_left <= distance_above and distance_left <= distance_upper_left:
        return left
    if distance_above <= distance_upper_left:
        return above
    return upper_left


def decode_png(path: Path) -> tuple[int, int, int, bytes]:
    payload = path.read_bytes()
    if not payload.startswith(PNG_SIGNATURE):
        raise ScreenshotError("invalid PNG signature")

    offset = len(PNG_SIGNATURE)
    header: tuple[int, int, int, int, int, int, int] | None = None
    compressed = bytearray()
    saw_end = False
    while offset + 12 <= len(payload):
        length = struct.unpack_from(">I", payload, offset)[0]
        offset += 4
        chunk_type = payload[offset : offset + 4]
        offset += 4
        if offset + length + 4 > len(payload):
            raise ScreenshotError("truncated PNG chunk")
        chunk = payload[offset : offset + length]
        offset += length
        expected_crc = struct.unpack_from(">I", payload, offset)[0]
        offset += 4
        if zlib.crc32(chunk_type + chunk) & 0xFFFFFFFF != expected_crc:
            raise ScreenshotError("PNG chunk checksum mismatch")
        if chunk_type == b"IHDR":
            if header is not None or length != 13:
                raise ScreenshotError("invalid PNG header")
            header = struct.unpack(">IIBBBBB", chunk)
        elif chunk_type == b"IDAT":
            compressed.extend(chunk)
        elif chunk_type == b"IEND":
            saw_end = True
            break

    if header is None or not saw_end or not compressed:
        raise ScreenshotError("incomplete PNG")
    width, height, bit_depth, color_type, compression, filtering, interlace = header
    if width <= 0 or height <= 0:
        raise ScreenshotError("invalid PNG dimensions")
    if bit_depth != 8 or color_type not in CHANNELS:
        raise ScreenshotError("only 8-bit grayscale, RGB, and RGBA PNGs are supported")
    if compression != 0 or filtering != 0 or interlace != 0:
        raise ScreenshotError("unsupported PNG encoding")

    channels = CHANNELS[color_type]
    row_bytes = width * channels
    try:
        encoded = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ScreenshotError(f"invalid PNG image stream: {error}") from error
    if len(encoded) != height * (row_bytes + 1):
        raise ScreenshotError("unexpected PNG image-stream length")

    decoded = bytearray(height * row_bytes)
    previous = bytearray(row_bytes)
    source_offset = 0
    for row_index in range(height):
        filter_type = encoded[source_offset]
        source_offset += 1
        source = encoded[source_offset : source_offset + row_bytes]
        source_offset += row_bytes
        current = bytearray(row_bytes)
        for index, value in enumerate(source):
            left = current[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                reconstructed = value
            elif filter_type == 1:
                reconstructed = value + left
            elif filter_type == 2:
                reconstructed = value + above
            elif filter_type == 3:
                reconstructed = value + ((left + above) // 2)
            elif filter_type == 4:
                reconstructed = value + _paeth(left, above, upper_left)
            else:
                raise ScreenshotError(f"unknown PNG row filter {filter_type}")
            current[index] = reconstructed & 0xFF
        start = row_index * row_bytes
        decoded[start : start + row_bytes] = current
        previous = current
    return width, height, color_type, bytes(decoded)


def measure_pixels(width: int, height: int, color_type: int, pixels: bytes) -> dict[str, object]:
    channels = CHANNELS[color_type]
    nonblack = 0
    opaque = 0
    red = 0
    cyan = 0
    red_x_total = 0
    cyan_x_total = 0
    red_bounds = [width, height, -1, -1]
    cyan_bounds = [width, height, -1, -1]
    minimum = 255
    maximum = 0
    buckets: set[tuple[int, int, int]] = set()
    bucket_counts: dict[tuple[int, int, int], int] = {}
    edge_count = 0
    edge_comparisons = 0
    previous_row_luminance = [0] * width
    for offset in range(0, len(pixels), channels):
        pixel_index = offset // channels
        x = pixel_index % width
        y = pixel_index // width
        if color_type in (0, 4):
            r = g = b = pixels[offset]
        else:
            r, g, b = pixels[offset : offset + 3]
        alpha = pixels[offset + channels - 1] if color_type in (4, 6) else 255
        luminance = (54 * r + 183 * g + 19 * b) // 256
        if x > 0:
            edge_comparisons += 1
            if abs(luminance - previous_luminance) >= 16:
                edge_count += 1
        if y > 0:
            edge_comparisons += 1
            if abs(luminance - previous_row_luminance[x]) >= 16:
                edge_count += 1
        previous_luminance = luminance
        previous_row_luminance[x] = luminance
        minimum = min(minimum, luminance)
        maximum = max(maximum, luminance)
        if max(r, g, b) > 16:
            nonblack += 1
        if alpha >= 250:
            opaque += 1
        if r >= 150 and r * 5 >= g * 7 and r * 5 >= b * 6:
            red += 1
            red_x_total += x
            red_bounds = [
                min(red_bounds[0], x), min(red_bounds[1], y),
                max(red_bounds[2], x), max(red_bounds[3], y),
            ]
        if g >= 120 and b >= 120 and min(g, b) * 5 >= r * 7:
            cyan += 1
            cyan_x_total += x
            cyan_bounds = [
                min(cyan_bounds[0], x), min(cyan_bounds[1], y),
                max(cyan_bounds[2], x), max(cyan_bounds[3], y),
            ]
        bucket = (r // 16, g // 16, b // 16)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(buckets) < 4096:
            buckets.add(bucket)

    total = width * height
    return {
        "pixels": total,
        "nonblack_pixels": nonblack,
        "nonblack_ratio": nonblack / total,
        "opaque_pixels": opaque,
        "opaque_ratio": opaque / total,
        "red_pixels": red,
        "cyan_pixels": cyan,
        "red_bounds": red_bounds if red else None,
        "cyan_bounds": cyan_bounds if cyan else None,
        "red_centroid_x_ratio": red_x_total / red / width if red else None,
        "cyan_centroid_x_ratio": cyan_x_total / cyan / width if cyan else None,
        "luminance_min": minimum,
        "luminance_max": maximum,
        "luminance_span": maximum - minimum,
        "color_buckets": len(buckets),
        "dominant_color_ratio": max(bucket_counts.values(), default=0) / total,
        "edge_ratio": edge_count / edge_comparisons if edge_comparisons else 0.0,
    }


def validate(arguments: argparse.Namespace) -> dict[str, object]:
    width, height, color_type, pixels = decode_png(arguments.image)
    metrics = measure_pixels(width, height, color_type, pixels)
    failures: list[str] = []
    if width < arguments.min_width or height < arguments.min_height:
        failures.append(f"dimensions {width}x{height} are below the required minimum")
    if metrics["nonblack_ratio"] < arguments.min_nonblack_ratio:
        failures.append("image does not contain enough non-black pixels")
    if metrics["opaque_ratio"] < arguments.min_opaque_ratio:
        failures.append("image does not contain enough opaque pixels")
    if metrics["luminance_span"] < arguments.min_luminance_span:
        failures.append("image does not contain enough luminance contrast")
    if metrics["color_buckets"] < arguments.min_color_buckets:
        failures.append("image does not contain enough color diversity")
    if metrics["dominant_color_ratio"] > arguments.max_dominant_color_ratio:
        failures.append("image is dominated by a single coarse color")
    if metrics["edge_ratio"] < arguments.min_edge_ratio:
        failures.append("image does not contain enough spatial detail")
    if metrics["red_pixels"] < arguments.require_red_pixels:
        failures.append("image does not contain the required red fixture pixels")
    if metrics["cyan_pixels"] < arguments.require_cyan_pixels:
        failures.append("image does not contain the required cyan fixture pixels")
    if arguments.require_red_left and (
        metrics["red_centroid_x_ratio"] is None or metrics["red_centroid_x_ratio"] >= 0.5
    ):
        failures.append("red fixture is not centered in the left half")
    if arguments.require_cyan_right and (
        metrics["cyan_centroid_x_ratio"] is None or metrics["cyan_centroid_x_ratio"] <= 0.5
    ):
        failures.append("cyan fixture is not centered in the right half")
    return {
        "passed": not failures,
        "image": arguments.image.name,
        "width": width,
        "height": height,
        **metrics,
        "failures": failures,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--min-width", type=int, default=640)
    parser.add_argument("--min-height", type=int, default=360)
    parser.add_argument("--min-nonblack-ratio", type=float, default=0.001)
    parser.add_argument("--min-opaque-ratio", type=float, default=0.99)
    parser.add_argument("--min-luminance-span", type=int, default=20)
    parser.add_argument("--min-color-buckets", type=int, default=4)
    parser.add_argument("--max-dominant-color-ratio", type=float, default=1.0)
    parser.add_argument("--min-edge-ratio", type=float, default=0.0)
    parser.add_argument("--require-red-pixels", type=int, default=0)
    parser.add_argument("--require-cyan-pixels", type=int, default=0)
    parser.add_argument("--require-red-left", action="store_true")
    parser.add_argument("--require-cyan-right", action="store_true")
    arguments = parser.parse_args()
    if arguments.min_width <= 0 or arguments.min_height <= 0:
        parser.error("minimum dimensions must be positive")
    for name in (
        "min_nonblack_ratio",
        "min_opaque_ratio",
        "max_dominant_color_ratio",
        "min_edge_ratio",
    ):
        value = getattr(arguments, name)
        if not 0.0 <= value <= 1.0:
            parser.error(f"--{name.replace('_', '-')} must be between zero and one")
    for name in (
        "min_luminance_span",
        "min_color_buckets",
        "require_red_pixels",
        "require_cyan_pixels",
    ):
        if getattr(arguments, name) < 0:
            parser.error(f"--{name.replace('_', '-')} must not be negative")
    return arguments


def main() -> int:
    arguments = parse_arguments()
    result: dict[str, object]
    try:
        result = validate(arguments)
    except (OSError, ScreenshotError) as error:
        result = {
            "passed": False,
            "image": arguments.image.name,
            "failures": [str(error)],
        }
    serialized = json.dumps(result, sort_keys=True)
    print(serialized, flush=True)
    if arguments.result:
        arguments.result.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            arguments.result,
            os.O_CREAT | os.O_TRUNC | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(serialized + "\n")
        os.chmod(arguments.result, 0o600)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
