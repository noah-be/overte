#!/usr/bin/env python3
"""Device-free state-reset contract for Pico OpenXR controller input."""

import hashlib
import json
from pathlib import Path
import re
import unittest


SOURCE = (
    Path(__file__).resolve().parents[4]
    / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrInputPlugin.cpp"
).read_text(encoding="utf-8")
HEADER = (
    Path(__file__).resolve().parents[4]
    / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrInputPlugin.h"
).read_text(encoding="utf-8")
CONTEXT = (
    Path(__file__).resolve().parents[4]
    / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrContext.cpp"
).read_text(encoding="utf-8")
CONTEXT_HEADER = (
    Path(__file__).resolve().parents[4]
    / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrContext.h"
).read_text(encoding="utf-8")
DESKTOP_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "plugins/openxr/src/OpenXrInputPlugin.cpp"
).read_text(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[4]
E2E_ROOT = ROOT / "android/vr/pico/apps/picoInterface/openxr/e2e_input"
PROFILE_PATH = ROOT / "tests/device/openxr_input/profiles/pico4-overte-controller.json"
PROFILE_ID = "overte-pico4-controller-v1"
PROFILE_SHA256 = "922e091c38f5cb1ec6c3e55c80b81de0a876524d951318c61e7feb4821eab481"


class OpenXrInputStateTest(unittest.TestCase):
    def test_e2e_axes_are_published_as_valid_and_scoped_to_the_debug_build(self):
        self.assertIn("#if defined(OVERTE_E2E_OPENXR_INPUT_V1)", SOURCE)
        self.assertIn(
            "_axisStateMap[y_channel] = AxisValue(-action.currentState.y, 0);",
            SOURCE,
        )
        self.assertIn(
            "_axisStateMap[channel] = AxisValue(action.currentState, 0);",
            SOURCE,
        )
        self.assertIn('"OVERTE_E2E_CONTROLLER_AXIS"', SOURCE)
        self.assertIn("e2eControllerOverrideActive", SOURCE)
        self.assertIn("!e2eControllerOverrideActive", SOURCE)

    def test_e2e_controller_stays_registered_for_every_injected_control(self):
        override = re.search(
            r"bool e2eControllerOverrideActive = false;(.*?)#endif",
            SOURCE,
            re.DOTALL,
        )
        self.assertIsNotNone(override)
        body = override.group(1)
        self.assertIn("controller::LY", body)
        self.assertIn("leftY->second.valid", body)
        self.assertNotIn("std::abs(leftY->second.value)", body)
        self.assertIn("controller::LEFT_SECONDARY_THUMB", body)
        self.assertIn("controller::RIGHT_SECONDARY_THUMB", body)

    def test_native_e2e_layer_identity_and_release_exclusion_are_mechanical(self):
        header = (E2E_ROOT / "E2eInputProtocol.h").read_text(encoding="utf-8")
        protocol = (E2E_ROOT / "E2eInputProtocol.cpp").read_text(encoding="utf-8")
        layer = (E2E_ROOT / "XrApiLayer.cpp").read_text(encoding="utf-8")
        openxr_root = E2E_ROOT.parent
        cmake = (openxr_root / "CMakeLists.txt").read_text(encoding="utf-8")
        app_root = openxr_root.parent
        gradle = (app_root / "build.gradle").read_text(encoding="utf-8")
        context = (openxr_root / "src/OpenXrContext.cpp").read_text(encoding="utf-8")
        manifest_path = (
            app_root
            / "src/debug/assets/openxr/1/api_layers/explicit.d/overte_e2e_input.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        fingerprint = hashlib.sha256(
            json.dumps(
                profile,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        self.assertEqual(PROFILE_ID, profile["profileId"])
        self.assertEqual(PROFILE_SHA256, fingerprint)
        self.assertIn(fingerprint, header)
        self.assertIn("XR_APILAYER_OVERTE_e2e_input", header)
        self.assertIn(
            "/data/user/0/org.overte.pico/files/overte-e2e/openxr-input",
            header,
        )
        for controls in profile["controls"].values():
            for action_name in controls.values():
                self.assertIn(f'"{action_name}"', protocol)
        self.assertNotIn('"system_click"', protocol)
        self.assertIn("XR_REFERENCE_SPACE_TYPE_STAGE", layer)
        self.assertIn('visibility("default")', layer)
        self.assertIn("xrNegotiateLoaderApiLayerInterface", layer)
        self.assertIn("if(ANDROID AND OVERTE_PICO_E2E_OPENXR_INPUT)", cmake)
        self.assertIn("arguments '-DOVERTE_PICO_E2E_OPENXR_INPUT=ON'", gradle)
        self.assertIn("arguments '-DOVERTE_PICO_E2E_OPENXR_INPUT=OFF'", gradle)
        self.assertIn("enabledApiLayerNames = &E2E_INPUT_LAYER", context)
        self.assertGreaterEqual(protocol.count("0.1, 8.0"), 2)
        self.assertIn('exactKeys(arguments, {}, { "holdMilliseconds" })', protocol)
        self.assertIn('operation == QLatin1String("input.jump")', protocol)
        self.assertIn('operation == QLatin1String("input.fly")', protocol)
        self.assertIn("constexpr std::int64_t JUMP_HOLD_MS = 450", protocol)
        self.assertIn("duration = JUMP_HOLD_MS", protocol)
        self.assertIn(
            "cursor += JUMP_HOLD_MS;\n"
            "            compiled.push_back({ cursor, neutralOverride(), {} });\n"
            "            cursor += INTER_COMMAND_GAP_MS;",
            protocol,
        )
        self.assertIn("BooleanChannel::RightSecondary", protocol)
        self.assertIn('{ "rightSecondaryApplied",', protocol)
        self.assertIn(
            "integerValue(arguments.value(\"holdMilliseconds\"), 100, 8000, hold)",
            protocol,
        )
        self.assertIn("std::uint64_t hold { 120 }", protocol)
        self.assertIn("recordViewApplication", header)
        self.assertIn('{ "viewAppliedSequence",', protocol)
        self.assertGreaterEqual(
            layer.count("recordViewApplication(epochMilliseconds())"), 2
        )
        self.assertIn("recordVectorApplication", header)
        self.assertIn("recordBooleanApplication", header)
        self.assertIn('{ "vectorAppliedSequence",', protocol)
        self.assertIn('{ "booleanAppliedSequence",', protocol)
        self.assertEqual(
            "XR_APILAYER_OVERTE_e2e_input", manifest["api_layer"]["name"]
        )
        self.assertEqual(
            "libXrApiLayer_overte_e2e_input.so",
            manifest["api_layer"]["library_path"],
        )
        release_manifest = app_root / "src/release/assets/openxr/1/api_layers/explicit.d"
        self.assertFalse(release_manifest.exists())

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

    def test_failed_hand_tracker_creation_is_not_published(self):
        start = SOURCE.index("if (_context->_handTrackingSupported)")
        end = SOURCE.index("if (_context->_MNDX_xdevSpaceSupported)", start)
        creation = SOURCE[start:end]
        self.assertIn("XrHandTrackerEXT candidate { XR_NULL_HANDLE }", creation)
        call = creation.index("xrCreateHandTrackerEXT")
        check = creation.index("if (xrCheck", call)
        publish = creation.index("_handTracker[index] = candidate", check)
        self.assertLess(call, check)
        self.assertLess(check, publish)
        self.assertNotIn("&_handTracker[", creation)
        self.assertIn("createHandTracker(0, XR_HAND_LEFT_EXT", creation)
        self.assertIn("createHandTracker(1, XR_HAND_RIGHT_EXT", creation)

    def test_required_hand_paths_publish_atomically(self):
        start = CONTEXT.index("XrPath leftHandPath { XR_NULL_PATH }")
        end = CONTEXT.index("return true;", start)
        paths = CONTEXT[start:end]
        left_call = paths.index('xrStringToPath(_instance, "/user/hand/left"')
        left_check = paths.index('"Failed to resolve left-hand OpenXR user path"', left_call)
        right_call = paths.index('xrStringToPath(_instance, "/user/hand/right"', left_check)
        right_check = paths.index('"Failed to resolve right-hand OpenXR user path"', right_call)
        publish_left = paths.index("_handPaths[0] = leftHandPath", right_check)
        publish_right = paths.index("_handPaths[1] = rightHandPath", publish_left)
        self.assertLess(left_call, left_check)
        self.assertLess(left_check, right_call)
        self.assertLess(right_call, right_check)
        self.assertLess(right_check, publish_left)
        self.assertLess(publish_left, publish_right)
        self.assertIn(
            "XrPath _handPaths[HAND_COUNT] { XR_NULL_PATH, XR_NULL_PATH }",
            CONTEXT_HEADER,
        )

        optional = paths.index('"/interaction_profiles/htc/vive_controller"', publish_right)
        optional_check = paths.index('"Failed to resolve optional Vive controller profile path"', optional)
        optional_publish = paths.index("_viveControllerPath = viveControllerPath", optional_check)
        self.assertLess(optional, optional_check)
        self.assertLess(optional_check, optional_publish)

    def test_null_interaction_profile_clears_hack_without_path_conversion(self):
        poll_start = CONTEXT.index("bool OpenXrContext::pollEvents()")
        profile_case = CONTEXT.index(
            "case XR_TYPE_EVENT_DATA_INTERACTION_PROFILE_CHANGED", poll_start)
        next_case = CONTEXT.index("case XR_TYPE_EVENT_DATA_USER_PRESENCE_CHANGED_EXT", profile_case)
        profile = CONTEXT[profile_case:next_case]
        query = profile.index("xrGetCurrentInteractionProfile")
        hack = profile.index("_vivePoseHack[i] =", query)
        null_check = profile.index("state.interactionProfile == XR_NULL_PATH", hack)
        null_continue = profile.index("continue;", null_check)
        convert = profile.index("xrPathToString", null_continue)
        self.assertLess(query, hack)
        self.assertLess(hack, null_check)
        self.assertLess(null_check, null_continue)
        self.assertLess(null_continue, convert)

    def test_published_hand_trackers_are_destroyed_idempotently(self):
        start = SOURCE.index("OpenXrInputPlugin::InputDevice::~InputDevice()")
        end = SOURCE.index("void OpenXrInputPlugin::InputDevice::focusOutEvent", start)
        cleanup = SOURCE[start:end]
        self.assertIn("std::unique_lock<std::recursive_mutex> locker(_lock)", cleanup)
        self.assertIn("for (auto& tracker : _handTracker)", cleanup)
        null_check = cleanup.index("tracker != XR_NULL_HANDLE")
        session_check = cleanup.index("_context->_session != XR_NULL_HANDLE", null_check)
        function_check = cleanup.index("_context->xrDestroyHandTrackerEXT", session_check)
        destroy = cleanup.index("xrDestroyHandTrackerEXT(tracker)", function_check)
        clear = cleanup.index("tracker = XR_NULL_HANDLE", destroy)
        self.assertLess(null_check, session_check)
        self.assertLess(session_check, destroy)
        self.assertLess(destroy, clear)
        xdev_loop = cleanup.index("for (auto& entry : _xdev)", clear)
        xdev_guard = cleanup.index("tracker.space != XR_NULL_HANDLE", xdev_loop)
        xdev_destroy = cleanup.index("xrDestroySpace(tracker.space)", xdev_guard)
        xdev_clear = cleanup.index("tracker.space = XR_NULL_HANDLE", xdev_destroy)
        xdev_map_clear = cleanup.index("_xdev.clear()", xdev_clear)
        actions = cleanup.index("_actions.clear()", xdev_map_clear)
        self.assertLess(xdev_loop, xdev_guard)
        self.assertLess(xdev_guard, xdev_destroy)
        self.assertLess(xdev_destroy, xdev_clear)
        self.assertLess(xdev_clear, xdev_map_clear)
        self.assertLess(xdev_map_clear, actions)
        action_set_check = cleanup.index("_actionSet != XR_NULL_HANDLE", actions)
        action_set_destroy = cleanup.index("xrDestroyActionSet(_actionSet)", action_set_check)
        action_set_clear = cleanup.index("_actionSet = XR_NULL_HANDLE", action_set_destroy)
        initialized_clear = cleanup.index("_actionsInitialized = false", action_set_clear)
        self.assertLess(actions, action_set_check)
        self.assertLess(action_set_check, action_set_destroy)
        self.assertLess(action_set_destroy, action_set_clear)
        self.assertLess(action_set_clear, initialized_clear)
        self.assertIn("~InputDevice() override", HEADER)

    def test_action_pose_spaces_follow_action_lifetime(self):
        start = SOURCE.index("OpenXrInputPlugin::Action::~Action()")
        end = SOURCE.index("XrActionStateFloat OpenXrInputPlugin::Action::getFloat", start)
        cleanup = SOURCE[start:end]
        null_check = cleanup.index("_poseSpace != XR_NULL_HANDLE")
        session_check = cleanup.index("_context->_session != XR_NULL_HANDLE", null_check)
        destroy = cleanup.index("xrDestroySpace(_poseSpace)", session_check)
        clear = cleanup.index("_poseSpace = XR_NULL_HANDLE", destroy)
        self.assertLess(null_check, session_check)
        self.assertLess(session_check, destroy)
        self.assertLess(destroy, clear)
        self.assertIn("~Action();", HEADER)

    def test_xdev_capability_requires_every_used_function(self):
        walk = CONTEXT.index("auto next = reinterpret_cast<const XrExtensionProperties*>")
        start = CONTEXT.index("XR_TYPE_SYSTEM_XDEV_SPACE_PROPERTIES_MNDX", walk)
        end = CONTEXT.index("// don't start up hand tracking stuff", start)
        xdev = CONTEXT[start:end]
        for name in (
                "xrCreateXDevListMNDX",
                "xrEnumerateXDevsMNDX",
                "xrGetXDevPropertiesMNDX",
                "xrDestroyXDevListMNDX",
                "xrCreateXDevSpaceMNDX"):
            self.assertIn('loadXrFunction(_instance, "' + name + '"', xdev)
            self.assertIn(name + " = nullptr", xdev)
        failure = xdev.index("if (!xdevFunctionsLoaded)")
        self.assertIn("_MNDX_xdevSpaceSupported = false", xdev[failure:])
        self.assertNotIn("xrGetInstanceProcAddr(", xdev)

    def test_vive_tracker_capability_requires_its_runtime_function(self):
        start = CONTEXT.index("// disable the MNDX tracker extension")
        end = CONTEXT.index("if (_userPresenceAvailable)", start)
        vive = CONTEXT[start:end]
        load = vive.index('loadXrFunction(_instance, "xrEnumerateViveTrackerPathsHTCX"')
        select = vive.index("_MNDX_xdevSpaceSupported = false", load)
        failure = vive.index("_HTCX_viveTrackerInteractionSupported = false", select)
        clear = vive.index("xrEnumerateViveTrackerPathsHTCX = nullptr", failure)
        self.assertLess(load, select)
        self.assertLess(select, failure)
        self.assertLess(failure, clear)
        self.assertNotIn("xrGetInstanceProcAddr(", vive)

    def test_body_tracker_poses_require_complete_valid_locations(self):
        self.assertIn(
            "XR_SPACE_LOCATION_ORIENTATION_VALID_BIT | XR_SPACE_LOCATION_POSITION_VALID_BIT",
            SOURCE,
        )
        guess_start = SOURCE.index("void OpenXrInputPlugin::guessXDevRoles")
        guess_end = SOURCE.index("void OpenXrInputPlugin::calibrate()", guess_start)
        guess = SOURCE[guess_start:guess_end]
        self.assertIn("XrTime sampleTime", guess)
        self.assertNotIn("_lastPredictedDisplayTime", guess)
        first_locate = guess.index("xrLocateSpace(")
        validity = guess.index("REQUIRED_POSE_LOCATION_FLAGS", first_locate)
        height_guard = guess.index("std::numeric_limits<float>::epsilon()", validity)
        division = guess.index("stageSpace.pose.position.y / headSpace.pose.position.y", height_guard)
        self.assertLess(first_locate, validity)
        self.assertLess(validity, height_guard)
        self.assertLess(height_guard, division)
        self.assertEqual(guess.count("sampleTime, &"), 3)
        self.assertIn("!stageLocated || !localLocated || !headLocated", guess)

        vive_start = SOURCE.index("void OpenXrInputPlugin::InputDevice::updateBodyFromViveTrackers")
        xdev_start = SOURCE.index("void OpenXrInputPlugin::InputDevice::updateBodyFromXDevSpaces")
        vive = SOURCE[vive_start:xdev_start]
        xdev = SOURCE[xdev_start:]
        self.assertIn("REQUIRED_POSE_LOCATION_FLAGS) == REQUIRED_POSE_LOCATION_FLAGS", vive)
        self.assertIn("REQUIRED_POSE_LOCATION_FLAGS) == REQUIRED_POSE_LOCATION_FLAGS", xdev)

    def test_uncalibrate_clears_published_xdev_roles_by_reference(self):
        start = SOURCE.index("bool OpenXrInputPlugin::uncalibrate()")
        end = SOURCE.index("bool OpenXrInputPlugin::isSupported()", start)
        uncalibrate = SOURCE[start:end]
        role_loop = uncalibrate.index("for (auto& [_, tracker] : _inputDevice->_xdev)")
        role_clear = uncalibrate.index("tracker.pose_channel = {}", role_loop)
        calibration_clear = uncalibrate.index("_trackerCalibrations.clear()", role_clear)
        pending_clear = uncalibrate.index("_wantsCalibrate = false", calibration_clear)
        self.assertLess(role_loop, role_clear)
        self.assertLess(role_clear, calibration_clear)
        self.assertLess(calibration_clear, pending_clear)
        self.assertNotIn("for (auto [_, tracker]", uncalibrate)

    def test_calibration_settings_validate_and_preserve_quaternion_order(self):
        for source in (SOURCE, DESKTOP_SOURCE):
            start = source.index("void OpenXrInputPlugin::setConfigurationSettings")
            end = source.index("QJsonObject OpenXrInputPlugin::configurationSettings()", start)
            settings = source[start:end]
            sizes = settings.index("values.size() != expectedSize")
            numeric = settings.index("!value.isDouble()", sizes)
            finite = settings.index("!std::isfinite(value.toDouble())", numeric)
            construct = settings.index("quat(rotationArray[3].toDouble()", finite)
            norm_guard = settings.index("rotationLength <= std::numeric_limits<float>::epsilon()", construct)
            publish = settings.index("rotation / rotationLength", norm_guard)
            self.assertLess(sizes, numeric)
            self.assertLess(numeric, finite)
            self.assertLess(finite, construct)
            self.assertLess(construct, norm_guard)
            self.assertLess(norm_guard, publish)
            self.assertIn("finiteNumbers(translationArray, 3)", settings)
            self.assertIn("finiteNumbers(rotationArray, 4)", settings)

            serializer = source[end:source.index("QString OpenXrInputPlugin::configurationLayout", end)]
            self.assertIn("QJsonArray { rotation.x, rotation.y, rotation.z, rotation.w }", serializer)

    def test_calibration_request_waits_for_a_valid_tracker_sample(self):
        for source in (SOURCE, DESKTOP_SOURCE):
            start = source.index("void OpenXrInputPlugin::InputDevice::calibratePucks")
            end = source.index("void OpenXrInputPlugin::InputDevice::updateBodyFromViveTrackers", start)
            calibrate = source[start:end]
            pending = calibrate.index("bool calibratedAny = false")
            lookup = calibrate.index("_poseStateMap.find(channel)", pending)
            missing = calibrate.index("pose == _poseStateMap.end()", lookup)
            validity = calibrate.index("!pose->second.isValid()", missing)
            publish = calibrate.index("_trackerCalibrations[channel]", validity)
            success = calibrate.index("calibratedAny = true", publish)
            retain = calibrate.index("_wantsCalibrate = !calibratedAny", success)
            self.assertLess(pending, lookup)
            self.assertLess(lookup, missing)
            self.assertLess(missing, validity)
            self.assertLess(validity, publish)
            self.assertLess(publish, success)
            self.assertLess(success, retain)
            self.assertNotIn("_poseStateMap[channel]", calibrate)

    def test_pending_xdev_calibration_retries_role_inference_under_lock(self):
        for source, is_pico in ((SOURCE, True), (DESKTOP_SOURCE, False)):
            calibrate_start = source.index("void OpenXrInputPlugin::calibrate()")
            calibrate_end = source.index("bool OpenXrInputPlugin::uncalibrate()", calibrate_start)
            request = source[calibrate_start:calibrate_end]
            self.assertIn("_trackerCalibrations.clear()", request)
            self.assertIn("_wantsCalibrate = true", request)
            self.assertNotIn("guessXDevRoles", request)

            update_start = source.index("void OpenXrInputPlugin::pluginUpdate")
            update_end = source.index("void OpenXrInputPlugin::loadSettings()", update_start)
            update = source[update_start:update_end]
            if is_pico:
                snapshot = update.index(
                    "const auto sampleTime = _context->_lastPredictedDisplayTime"
                )
            locked = update.index("userInputMapper->withLock")
            pending = update.index("_inputDevice->_wantsCalibrate", locked)
            backend = update.index("_context->_MNDX_xdevSpaceSupported", pending)
            if is_pico:
                time_guard = update.index("sampleTime.has_value()", backend)
                guess = update.index(
                    "guessXDevRoles(_inputDevice->_xdev, sampleTime.value())", time_guard
                )
                self.assertLess(snapshot, locked)
                self.assertLess(backend, time_guard)
                self.assertLess(time_guard, guess)
            else:
                guess = update.index("guessXDevRoles(_inputDevice->_xdev)", backend)
            device_update = update.index("_inputDevice->update(deltaTime, inputCalibrationData)", guess)
            self.assertLess(locked, pending)
            self.assertLess(pending, backend)
            self.assertLess(backend, guess)
            self.assertLess(guess, device_update)

    def test_xdev_role_inference_clears_stale_assignments_after_time_guard(self):
        for source, is_pico in ((SOURCE, True), (DESKTOP_SOURCE, False)):
            start = source.index("void OpenXrInputPlugin::guessXDevRoles")
            end = source.index("void OpenXrInputPlugin::calibrate()", start)
            guess = source[start:end]
            if is_pico:
                self.assertIn("XrTime sampleTime", guess)
                self.assertNotIn("_lastPredictedDisplayTime", guess)
                update_start = source.index("void OpenXrInputPlugin::pluginUpdate")
                update_end = source.index("void OpenXrInputPlugin::loadSettings()", update_start)
                update = source[update_start:update_end]
                time_guard = update.index("sampleTime.has_value()")
                inference = update.index(
                    "guessXDevRoles(_inputDevice->_xdev, sampleTime.value())", time_guard
                )
                self.assertLess(time_guard, inference)
                role_loop = guess.index("for (auto& [_, tracker] : tracker_map)")
            else:
                time_guard = guess.index("if (!_context->_lastPredictedDisplayTime.has_value())")
                role_loop = guess.index("for (auto& [_, tracker] : tracker_map)", time_guard)
            role_clear = guess.index("tracker.pose_channel.reset()", role_loop)
            locate_loop = guess.index("for (auto [id, tracker] : tracker_map)", role_clear)
            first_locate = guess.index("xrLocateSpace(", locate_loop)
            validity = guess.index("REQUIRED_POSE_LOCATION_FLAGS", first_locate)
            height_guard = guess.index("std::numeric_limits<float>::epsilon()", validity)
            assign = guess.index("state.pose_channel =", height_guard)
            if not is_pico:
                self.assertLess(time_guard, role_loop)
            self.assertLess(role_loop, role_clear)
            self.assertLess(role_clear, locate_loop)
            self.assertLess(locate_loop, first_locate)
            self.assertLess(first_locate, validity)
            self.assertLess(validity, height_guard)
            self.assertLess(height_guard, assign)

    def test_controller_pose_requires_position_and_orientation(self):
        for source in (SOURCE, DESKTOP_SOURCE):
            start = source.index("void OpenXrInputPlugin::InputDevice::update(")
            end = source.index("void OpenXrInputPlugin::InputDevice::setupControllerFlags", start)
            update = source[start:end]
            location = update.index("XrSpaceLocation handLocation")
            validity = update.index(
                "handLocation.locationFlags & REQUIRED_POSE_LOCATION_FLAGS", location
            )
            complete = update.index("== REQUIRED_POSE_LOCATION_FLAGS", validity)
            translation = update.index("handLocation.pose.position", complete)
            self.assertLess(location, validity)
            self.assertLess(validity, complete)
            self.assertLess(complete, translation)
            if source is SOURCE:
                tracked = update.index("++_trackedControllers", complete)
                self.assertLess(complete, tracked)
                self.assertLess(tracked, translation)

    def test_incomplete_palm_pose_falls_back_to_grip_pose(self):
        for source in (SOURCE, DESKTOP_SOURCE):
            start = source.index("void OpenXrInputPlugin::InputDevice::update(")
            end = source.index("void OpenXrInputPlugin::InputDevice::setupControllerFlags", start)
            update = source[start:end]
            initialized = update.index("XrSpaceLocation handLocation { .type = XR_TYPE_SPACE_LOCATION }")
            palm_get = update.index("const auto palmLocation", initialized)
            palm_flags = update.index(
                "palmLocation.locationFlags & REQUIRED_POSE_LOCATION_FLAGS", palm_get
            )
            select = update.index("handLocation = palmLocation", palm_flags)
            palm_selected = update.index("usingPalm = true", select)
            fallback = update.index("if (!usingPalm)", palm_selected)
            grip_get = update.index("_actions.at(grip_path)->getPose()", fallback)
            final_flags = update.index(
                "handLocation.locationFlags & REQUIRED_POSE_LOCATION_FLAGS", grip_get
            )
            self.assertLess(initialized, palm_get)
            self.assertLess(palm_get, palm_flags)
            self.assertLess(palm_flags, select)
            self.assertLess(select, palm_selected)
            self.assertLess(palm_selected, fallback)
            self.assertLess(fallback, grip_get)
            self.assertLess(grip_get, final_flags)
            self.assertNotIn("isPoseActive()", update[initialized:final_flags])

    def test_removed_split_pose_activity_query_stays_removed(self):
        desktop_header = (
            Path(__file__).resolve().parents[4]
            / "plugins/openxr/src/OpenXrInputPlugin.h"
        ).read_text(encoding="utf-8")
        for source, header in ((SOURCE, HEADER), (DESKTOP_SOURCE, desktop_header)):
            self.assertNotIn("isPoseActive()", source)
            self.assertNotIn("isPoseActive()", header)
            self.assertIn("XrSpaceLocation getPose()", header)

    def test_xdev_enumeration_and_space_publication_are_transactional(self):
        start = SOURCE.index("if (_context->_MNDX_xdevSpaceSupported)")
        end = SOURCE.index("_actionsInitialized = true", start)
        xdev = SOURCE[start:end]
        self.assertIn("XrXDevListMNDX xdevList { XR_NULL_HANDLE }", xdev)
        self.assertIn('"Failed to create XDev list"', xdev)
        self.assertIn('"Failed to enumerate XDevs"', xdev)
        self.assertIn("xdevIDsCount > MAX_TRACKER_COUNT", xdev)
        self.assertIn('"Failed to get XDev properties"', xdev)
        self.assertIn("!properties.canCreateSpace", xdev)
        candidate = xdev.index("XrSpace candidateSpace { XR_NULL_HANDLE }")
        create = xdev.index("xrCreateXDevSpaceMNDX", candidate)
        check = xdev.index('"Failed to create XDev space"', create)
        publish = xdev.index("tracker.space = candidateSpace", check)
        insert = xdev.index("_xdev.insert", publish)
        destroy_list = xdev.index("xrDestroyXDevListMNDX", insert)
        self.assertLess(candidate, create)
        self.assertLess(create, check)
        self.assertLess(check, publish)
        self.assertLess(publish, insert)
        self.assertLess(insert, destroy_list)


if __name__ == "__main__":
    unittest.main()
