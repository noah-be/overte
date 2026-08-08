#!/usr/bin/env python3
"""Device-free state-reset contract for Pico OpenXR controller input."""

from pathlib import Path
import re
import unittest


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "android/apps/picoInterface/openxr/src/OpenXrInputPlugin.cpp"
).read_text(encoding="utf-8")
HEADER = (
    Path(__file__).resolve().parents[2]
    / "android/apps/picoInterface/openxr/src/OpenXrInputPlugin.h"
).read_text(encoding="utf-8")
CONTEXT = (
    Path(__file__).resolve().parents[2]
    / "android/apps/picoInterface/openxr/src/OpenXrContext.cpp"
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

    def test_haptics_reject_non_hand_indices(self):
        haptics = re.search(
            r"bool OpenXrInputPlugin::InputDevice::triggerHapticPulse\(.*?\n\}",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(haptics)
        body = haptics.group(0)
        self.assertIn("index >= HAND_COUNT", body)
        self.assertNotIn("index > 2", body)
        self.assertIn("!std::isfinite(strength)", body)
        self.assertIn("!std::isfinite(duration)", body)
        self.assertIn("duration <= 0.0f", body)
        self.assertIn("std::numeric_limits<XrDuration>::max()", body)
        self.assertIn("static_cast<XrDuration>(durationNanoseconds)", body)
        self.assertNotIn("static_cast<int>(duration)", body)
        self.assertIn("!_actionsInitialized", body)
        self.assertIn("_context->_session == XR_NULL_HANDLE", body)
        self.assertIn("_actions.find(path)", body)
        self.assertIn("action == _actions.end()", body)
        self.assertIn("std::clamp(0.5f * strength, 0.0f, 1.0f)", body)
        failure = body.index("if (!action->second->applyHaptic")
        self.assertIn("return false;", body[failure:failure + 220])

    def test_required_actions_initialize_atomically(self):
        start = SOURCE.index("bool OpenXrInputPlugin::InputDevice::initActions()")
        end = SOURCE.index("void OpenXrInputPlugin::InputDevice::update", start)
        init = SOURCE[start:end]
        self.assertIn("auto discardUnattachedActionSet = [&]", init)
        self.assertIn("xrDestroyActionSet(_actionSet)", init)
        self.assertIn("_actionSet = XR_NULL_HANDLE", init)
        failure = init.index("if (!action->init(_actionSet))")
        rollback = init.index("discardUnattachedActionSet();", failure)
        failed_return = init.index("return false;", rollback)
        publish = init.index("_actions.emplace(id, action)", failure)
        self.assertLess(rollback, failed_return)
        self.assertLess(failed_return, publish)
        attach_failure = init.index('"Failed to attach action set"')
        self.assertIn("discardUnattachedActionSet();", init[attach_failure:attach_failure + 180])
        self.assertIn("XrActionSet _actionSet { XR_NULL_HANDLE };", HEADER)

    def test_binding_paths_are_checked_before_publication(self):
        start = SOURCE.index("bool OpenXrInputPlugin::InputDevice::initBindings")
        end = SOURCE.index("controller::Input::NamedVector", start)
        bindings = SOURCE[start:end]
        conversion = bindings.index("result = xrStringToPath", bindings.index("inputPathRaw"))
        check = bindings.index("if (!xrCheck", conversion)
        publish = bindings.index("suggestions.emplace", check)
        self.assertLess(conversion, check)
        self.assertLess(check, publish)
        self.assertIn("XrPath bindingPath { XR_NULL_PATH };", bindings)
        self.assertIn(".binding = bindingPath", bindings)
        self.assertNotIn("getBindings()", SOURCE)
        self.assertNotIn("getBindings();", HEADER)

    def test_hand_joints_fail_closed_before_pose_publication(self):
        start = SOURCE.index("void OpenXrInputPlugin::InputDevice::getHandTrackingInputs")
        end = SOURCE.index("void OpenXrInputPlugin::InputDevice::calibratePucks", start)
        hand = SOURCE[start:end]
        self.assertIn("XrHandJointLocationEXT joints[XR_HAND_JOINT_COUNT_EXT] {};", hand)
        locate = hand.index("xrLocateHandJointsEXT")
        check = hand.index('xrCheck(_context->_instance, result, "Failed to locate hand joints")', locate)
        active = hand.index("!locations.isActive", check)
        flags = hand.index("REQUIRED_JOINT_FLAGS", active)
        flag_check = hand.index("joint.locationFlags & REQUIRED_JOINT_FLAGS", flags)
        publish = hand.index("_poseStateMap[", flag_check)
        self.assertLess(locate, check)
        self.assertLess(check, active)
        self.assertLess(active, flag_check)
        self.assertLess(flag_check, publish)
        self.assertIn("XR_SPACE_LOCATION_POSITION_VALID_BIT", hand)
        self.assertIn("XR_SPACE_LOCATION_ORIENTATION_VALID_BIT", hand)

    def test_hand_tracking_capability_requires_every_function(self):
        extension_walk = CONTEXT.index("auto next = reinterpret_cast<const XrExtensionProperties*>")
        start = CONTEXT.index("XR_TYPE_SYSTEM_HAND_TRACKING_PROPERTIES_EXT", extension_walk)
        end = CONTEXT.index("XR_TYPE_SYSTEM_XDEV_SPACE_PROPERTIES_MNDX", start)
        hand = CONTEXT[start:end]
        self.assertIn('loadXrFunction(', hand)
        self.assertIn('"xrCreateHandTrackerEXT"', hand)
        self.assertIn('"xrDestroyHandTrackerEXT"', hand)
        self.assertIn('"xrLocateHandJointsEXT"', hand)
        failure = hand.index("if (!handFunctionsLoaded)")
        self.assertIn("_handTrackingSupported = false", hand[failure:])
        self.assertIn("xrCreateHandTrackerEXT = nullptr", hand[failure:])
        self.assertIn("xrDestroyHandTrackerEXT = nullptr", hand[failure:])
        self.assertIn("xrLocateHandJointsEXT = nullptr", hand[failure:])
        self.assertNotIn("xrGetInstanceProcAddr(", hand)


if __name__ == "__main__":
    unittest.main()
