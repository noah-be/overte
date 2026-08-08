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

    def test_view_counts_and_tracking_flags_are_fail_closed(self):
        self.assertIn("uint32_t eyeViewCount { 0 };", SOURCE)
        self.assertIn("eyeViewCount != _viewCount || eyeViewCount < 2", SOURCE)
        self.assertIn("uint32_t stageViewCount { 0 };", SOURCE)
        self.assertIn("stageViewCount != _viewCount", SOURCE)
        self.assertIn("XR_VIEW_STATE_ORIENTATION_VALID_BIT | XR_VIEW_STATE_POSITION_VALID_BIT", SOURCE)
        self.assertIn("(_lastViewState.viewStateFlags & REQUIRED_VIEW_FLAGS) != REQUIRED_VIEW_FLAGS", SOURCE)

    def test_invalid_head_location_preserves_last_valid_pose(self):
        locate = SOURCE.index("result = xrLocateSpace")
        result_check = SOURCE.index('xrCheck(_context->_instance, result, "Could not locate head space")', locate)
        flags_check = SOURCE.index("headLocation.locationFlags & REQUIRED_HEAD_FLAGS", result_check)
        pose_write = SOURCE.index("_context->_lastHeadPose =", flags_check)
        frame_write = SOURCE.index("_currentPresentFrameInfo.presentPose", pose_write)
        self.assertLess(result_check, flags_check)
        self.assertLess(flags_check, pose_write)
        self.assertLess(pose_write, frame_write)
        self.assertIn(
            "XR_SPACE_LOCATION_ORIENTATION_VALID_BIT | XR_SPACE_LOCATION_POSITION_VALID_BIT",
            SOURCE,
        )

    def test_view_initialization_is_stereo_and_transactional(self):
        start = SOURCE.index("bool OpenXrDisplayPlugin::initViews()")
        end = SOURCE.index("#define ENUM_TO_STR", start)
        body = SOURCE[start:end]
        self.assertIn("viewCount != REQUIRED_STEREO_VIEW_COUNT", body)
        self.assertIn("uint32_t populatedViewCount { 0 };", body)
        self.assertIn("populatedViewCount != viewCount", body)
        self.assertIn("recommendedImageRectWidth == 0", body)
        self.assertIn("recommendedImageRectHeight == 0", body)
        self.assertIn("recommendedSwapchainSampleCount == 0", body)
        self.assertLess(body.index("populatedViewCount != viewCount"), body.index("_viewCount = viewCount"))
        self.assertLess(body.index("recommendedImageRectWidth == 0"), body.index("_viewCount = viewCount"))
        self.assertNotIn("assert(_viewCount", body)


if __name__ == "__main__":
    unittest.main()
