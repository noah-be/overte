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

        tracked_reset = body.index("_trackedControllers = 0")
        self.assertLess(tracked_reset, no_session)

    def test_failed_action_sync_returns_with_neutral_maps(self):
        sync_guard = re.search(
            r"if \(!xrCheck\(instance, result, \"failed to sync actions!\"\)\) \{"
            r"\s*return;\s*\}",
            SOURCE,
        )
        self.assertIsNotNone(sync_guard)

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

    def test_only_valid_controller_poses_are_counted(self):
        valid_pose = re.search(
            r"if \(locationValid\) \{(.*?)\n        \}", SOURCE, re.DOTALL
        )
        self.assertIsNotNone(valid_pose)
        self.assertIn("++_trackedControllers", valid_pose.group(1))
        self.assertNotIn("_trackedControllers = 2", SOURCE)

    def test_action_getters_fail_closed(self):
        self.assertIn("return { .type = XR_TYPE_ACTION_STATE_FLOAT }", SOURCE)
        self.assertIn("return { .type = XR_TYPE_ACTION_STATE_VECTOR2F }", SOURCE)
        self.assertIn("return { .type = XR_TYPE_ACTION_STATE_BOOLEAN }", SOURCE)
        pose = re.search(
            r"XrSpaceLocation OpenXrInputPlugin::Action::getPose\(\) \{(.*?)\n\}",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(pose)
        body = pose.group(1)
        self.assertIn("!state.isActive", body)
        self.assertIn("return location", body)
        self.assertRegex(body, r"if \(!xrCheck\(.*Failed to locate hand space!")

    def test_pose_activity_failure_returns_false(self):
        active = re.search(
            r"bool OpenXrInputPlugin::Action::isPoseActive\(\) \{(.*?)\n\}",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(active)
        self.assertIn("return xrCheck", active.group(1))
        self.assertIn("&&\n        state.isActive", active.group(1))


if __name__ == "__main__":
    unittest.main()
