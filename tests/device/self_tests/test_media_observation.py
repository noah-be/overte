"""Reject stale video textures and unrelated DOM motion in media observations."""
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
from io import BytesIO
import importlib.util
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw, UnidentifiedImageError

DEVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE))
from media_observation import inspect_playback, inspect_reference_video

spec = importlib.util.spec_from_file_location("reference_generator", DEVICE / "fixture/parity/generate_video.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
ROI = (80, 60, 464, 276)


def capture(number, *, dom=0, frozen_square=None):
    video = Image.frombytes("RGB", (192, 108), generator.frame(number))
    if frozen_square is not None:
        # The encoded counter changes, but native video motion is broken.
        draw = ImageDraw.Draw(video)
        background = ((200, 32, 32), (32, 180, 32), (32, 32, 200))[number // 24]
        draw.rectangle((0, 68, 191, 88), fill=background)
        draw.rectangle((8 + frozen_square * 2 % 160, 70,
                        23 + frozen_square * 2 % 160, 85), fill="white")
    native = Image.new("RGB", (600, 340), "black")
    native.paste(video.resize((384, 216)), ROI[:2])
    draw = ImageDraw.Draw(native)
    draw.rectangle((dom * 5, 0, dom * 5 + 20, 30), fill="white")
    output = BytesIO()
    native.save(output, format="PNG")
    return output.getvalue()


class ReferenceVideoObservation(unittest.TestCase):
    def test_every_encoded_counter_color_and_square_matches(self):
        for number in range(72):
            with self.subTest(number=number):
                result = inspect_reference_video(capture(number), ROI)
                self.assertEqual(result["encodedFrame"], number)
                self.assertTrue(result["referencePixelsMatch"])

    def test_full_color_cycle_observes_pixels_without_claiming_acceptance(self):
        result = inspect_playback([(i, capture(i * 12)) for i in range(6)], ROI)
        self.assertTrue(result["movingReferenceVideoPixelsObserved"])
        self.assertFalse(result["deviceAcceptance"])

    def test_frozen_texture_with_moving_dom_does_not_count(self):
        result = inspect_playback([(i, capture(0, dom=i)) for i in range(6)], ROI)
        self.assertFalse(result["movingReferenceVideoPixelsObserved"])

    def test_counter_and_color_cannot_hide_a_frozen_encoded_square(self):
        result = inspect_playback([(i, capture(i * 12, frozen_square=0)) for i in range(6)], ROI)
        self.assertFalse(result["movingReferenceVideoPixelsObserved"])

    def test_black_or_wrong_selected_region_has_no_encoded_pixels(self):
        result = inspect_reference_video(capture(12), (80, 0, 176, 54))
        self.assertFalse(result["referencePixelsMatch"])

    def test_replayed_capture_timestamps_rejected(self):
        with self.assertRaises(ValueError):
            inspect_playback([(1, capture(i * 12)) for i in range(6)], ROI)

    def test_invalid_geometry_is_capture_error_not_product_failure(self):
        for roi in [(0, 0, 50, 28), (80, 60, 700, 276), (80, 60, 280, 260), (80., 60, 464, 276)]:
            with self.subTest(roi=roi), self.assertRaises(ValueError):
                inspect_reference_video(capture(0), roi)

    def test_invalid_image_and_nonfinite_time_rejected(self):
        with self.assertRaises(UnidentifiedImageError):
            inspect_reference_video(b"not an image", ROI)
        with self.assertRaises(ValueError):
            inspect_playback([(float("nan"), capture(0))] * 6, ROI)


if __name__ == "__main__":
    unittest.main()
