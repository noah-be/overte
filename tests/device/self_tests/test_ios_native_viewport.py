"""Reject stale, malformed and independently inconsistent input geometry."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios.viewport import viewport


class NativeViewport(unittest.TestCase):
    def setUp(self):
        self.observed = {"schemaVersion": 1, "sampleEpochMs": 10000, "sampleSequence": 1,
                         "nativeUi": {"valid": True, "surfaceWidth": 1024, "surfaceHeight": 768,
                                      "safeInsetLeft": 0, "safeInsetTop": 0,
                                      "safeInsetRight": 0, "safeInsetBottom": 0},
                         "window": {"width": 2048, "height": 1536}}

    def test_native_coordinates_allow_real_scaled_qt_surface(self):
        self.assertEqual(viewport(self.observed, 10000)["width"], 1024)

    def test_stale_invalid_and_rotating_surface_are_rejected(self):
        for path, value in [("sampleEpochMs", 5000), ("sampleEpochMs", float("nan")),
                            ("sampleSequence", True), ("nativeUi.valid", False),
                            ("window.width", 768), ("nativeUi.surfaceWidth", True)]:
            observed = copy.deepcopy(self.observed)
            keys = path.split(".")
            container = observed if len(keys) == 1 else observed[keys[0]]
            container[keys[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                viewport(observed, 10000)

    def test_native_safe_area_projects_content_without_guessing_offsets(self):
        self.observed["nativeUi"].update(surfaceWidth=1366, surfaceHeight=1024,
                                         safeInsetBottom=25)
        self.observed["window"] = {"width": 1366, "height": 999}
        self.assertEqual(viewport(self.observed, 10000),
                         {"x": 0, "y": 0, "width": 1366, "height": 999})
        self.observed["nativeUi"]["safeInsetBottom"] = 0
        with self.assertRaises(ValueError):
            viewport(self.observed, 10000)


if __name__ == "__main__":
    unittest.main()
