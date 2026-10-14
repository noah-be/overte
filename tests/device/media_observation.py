"""Recognize encoded reference-video pixels in an explicitly selected capture ROI.

This is image analysis, not proof of capture provenance, installed-artifact
identity, physical audibility, or complete device acceptance. Callers must retain
the native capture and its independent source/artifact/environment bindings.
"""
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
from io import BytesIO
import math
from statistics import median

WIDTH, HEIGHT = 192, 108
DIGITS = ("111101101101111", "010110010010111", "111001111100111",
          "111001111001111", "101101111001001", "111100111001111",
          "111100111101111", "111001001001001", "111101111101111",
          "111101111001111")


def _white(rgb):
    return min(rgb) >= 170 and max(rgb) - min(rgb) <= 55


def inspect_reference_video(content, roi):
    """Read a front-facing, tightly cropped video rectangle, excluding DOM/UI.

    ROI is (left, top, right, bottom) in the original PNG/JPEG capture. It must
    contain the entire video image without controls/borders. Small or perspective
    distorted surfaces need a better native capture; do not infer their frames.
    """
    from PIL import Image
    if not isinstance(content, bytes) or not 0 < len(content) <= 32 * 1024 * 1024:
        raise ValueError("Capture bytes exceed supported limits")
    if (not isinstance(roi, (tuple, list)) or len(roi) != 4
            or any(type(v) is not int for v in roi)):
        raise ValueError("Explicit integer video ROI required")
    left, top, right, bottom = roi
    with Image.open(BytesIO(content)) as original:
        if (original.format not in ("PNG", "JPEG") or original.width * original.height > 32_000_000
                or not 0 <= left < right <= original.width
                or not 0 <= top < bottom <= original.height
                or right - left < 96 or bottom - top < 54
                or abs((right - left) / (bottom - top) - WIDTH / HEIGHT) > .08):
            raise ValueError("Native video ROI is unusable; improve capture geometry")
        original.load()
        image = original.crop(roi).convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    pixels = image.load()
    numbers = []
    for position in range(3):
        cells = []
        for cell in range(15):
            x = 12 + position * 24 + cell % 3 * 5 + 2
            y = 12 + cell // 3 * 5 + 2
            rgb = tuple(median(pixels[x + dx, y + dy][channel]
                               for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                        for channel in range(3))
            cells.append("1" if _white(rgb) else "0")
        glyph = "".join(cells)
        if glyph not in DIGITS:
            return {"encodedFrame": None, "referencePixelsMatch": False, "reason": "encoded counter unavailable"}
        numbers.append(DIGITS.index(glyph))
    number = 100 * numbers[0] + 10 * numbers[1] + numbers[2]
    if number >= 72:
        return {"encodedFrame": None, "referencePixelsMatch": False, "reason": "counter outside reference"}
    expected_color = number // 24
    background = [pixels[x, y] for y in range(40, 62) for x in range(4, 188)]
    color_fraction = sum(rgb[expected_color] > 75
                         and all(rgb[expected_color] > 1.6 * rgb[c]
                                 for c in range(3) if c != expected_color)
                         for rgb in background) / len(background)
    square_left = 8 + number * 2 % 160
    inside = [pixels[x, y] for y in range(72, 84) for x in range(square_left + 2, square_left + 14)]
    outside = [pixels[x, y] for y in range(72, 84) for x in range(4, 188)
               if not square_left - 2 <= x < square_left + 18]
    square_fraction = sum(map(_white, inside)) / len(inside)
    extra_white_fraction = sum(map(_white, outside)) / len(outside)
    return {"encodedFrame": number, "referencePixelsMatch": color_fraction >= .85
            and square_fraction >= .85 and extra_white_fraction <= .02,
            "colorFraction": color_fraction, "squareFraction": square_fraction,
            "unexpectedWhiteFraction": extra_white_fraction}


def inspect_playback(samples, roi):
    """Observe playback from (monotonic seconds, native capture bytes) samples.

    Report only fixture pixels. A single frozen video frame, DOM motion, or a
    player-clock update cannot satisfy this observation. Native camera/ROI must
    remain fixed. Pause/resume/seek and sound are separate acceptance actions.
    """
    if not isinstance(samples, (tuple, list)) or not 6 <= len(samples) <= 96:
        raise ValueError("Six to 96 independent native samples required")
    observations = []
    times = []
    for when, content in samples:
        if type(when) not in (int, float) or not math.isfinite(when):
            raise ValueError("Finite monotonic sample time required")
        if times and when <= times[-1]:
            raise ValueError("Independent samples require increasing capture times")
        times.append(when)
        observations.append(inspect_reference_video(content, roi))
    frames = [row["encodedFrame"] for row in observations if row["referencePixelsMatch"]]
    observed = (len(frames) == len(samples) and len(set(frames)) >= 6
                and {n // 24 for n in frames} == {0, 1, 2} and times[-1] - times[0] >= 5)
    return {"qualification": "REFERENCE_VIDEO_PIXEL_OBSERVATION_ONLY",
            "movingReferenceVideoPixelsObserved": observed,
            "samples": observations, "deviceAcceptance": False,
            "limitations": "Capture provenance, source/artifact binding, fixed camera/ROI, pause/seek/lifecycle and physically audible output require independent evidence."}
