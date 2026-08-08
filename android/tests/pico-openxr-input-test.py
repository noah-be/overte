#!/usr/bin/env python3
"""Device-free state-reset contract for Pico OpenXR controller input."""

from pathlib import Path
import re
import unittest


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "android/apps/picoInterface/openxr/src/OpenXrInputPlugin.cpp"
).read_text(encoding="utf-8")


class OpenXrInputStateTest(unittest.TestCase):
    def test_transient_input_maps_reset_before_any_early_return(self):
        update = re.search(
            r"void OpenXrInputPlugin::InputDevice::update\(.*?\n\}",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(update)
        body = update.group(0)
        pose_clear = body.index("_poseStateMap.clear()")
        button_clear = body.index("_buttonPressedMap.clear()")
        axis_clear = body.index("_axisStateMap.clear()")
        no_session = body.index("if (_context->_session == XR_NULL_HANDLE)")
        sync = body.index("xrSyncActions")
        self.assertLess(pose_clear, no_session)
        self.assertLess(button_clear, no_session)
        self.assertLess(axis_clear, no_session)
        self.assertLess(axis_clear, sync)

    def test_inactive_float_actions_do_not_repopulate_axes(self):
        float_loop = re.search(
            r"for \(const auto& \[name, channel\] : floatsToUpdate\) \{(.*?)\n    \}",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(float_loop)
        body = float_loop.group(1)
        self.assertIn("if (action.isActive)", body)
        self.assertIn("_axisStateMap[channel].value = action.currentState", body)


if __name__ == "__main__":
    unittest.main()
