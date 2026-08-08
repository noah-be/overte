#!/usr/bin/env python3
"""Source contracts for fail-closed Pico OpenXR frame submission."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "android/apps/picoInterface/openxr/src/OpenXrDisplayPlugin.cpp").read_text(
    encoding="utf-8"
)
HEADER = (ROOT / "android/apps/picoInterface/openxr/src/OpenXrDisplayPlugin.h").read_text(
    encoding="utf-8"
)


class PicoOpenXRDisplayTests(unittest.TestCase):
    def test_failed_started_frame_uses_empty_layer_end(self):
        self.assertIn("bool endFrame(bool submitLayer = true);", HEADER)
        self.assertIn("auto failFrame = [&]", SOURCE)
        self.assertIn("releaseWaitedSwapChains();", SOURCE)
        self.assertIn("endFrame(false);", SOURCE)
        self.assertIn("if (!submitLayer ||", SOURCE)

    def test_only_successfully_waited_images_are_released(self):
        acquire = SOURCE.index("xrAcquireSwapchainImage")
        wait = SOURCE.index("xrWaitSwapchainImage", acquire)
        increment = SOURCE.index("++waitedSwapChains", wait)
        self.assertLess(acquire, wait)
        self.assertLess(wait, increment)
        self.assertIn(".timeout = XR_INFINITE_DURATION", SOURCE)
        self.assertIn("result == XR_TIMEOUT_EXPIRED", SOURCE)

    def test_every_swapchain_failure_path_finishes_frame(self):
        present_start = SOURCE.index("void OpenXrDisplayPlugin::hmdPresent()")
        present_end = SOURCE.index("bool OpenXrDisplayPlugin::endFrame", present_start)
        present = SOURCE[present_start:present_end]
        self.assertGreaterEqual(present.count("failFrame();"), 5)
        self.assertIn("if (!releaseWaitedSwapChains())", present)
        self.assertIn("if (!endFrame())", present)

    def test_resource_and_index_checks_precede_copy(self):
        resource_check = SOURCE.index("OpenXR stereo frame resources are incomplete")
        backend_check = SOURCE.index("if (!glBackend)", resource_check)
        index_check = SOURCE.index("_swapChainIndices[i] >= _images[i].size()", backend_check)
        copy = SOURCE.index("glCopyImageSubData", index_check)
        self.assertLess(resource_check, backend_check)
        self.assertLess(backend_check, index_check)
        self.assertLess(index_check, copy)


if __name__ == "__main__":
    unittest.main()
