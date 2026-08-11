#!/usr/bin/env python3
"""Source contracts for fail-closed Pico OpenXR frame submission."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[4]
SOURCE = (ROOT / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrDisplayPlugin.cpp").read_text(
    encoding="utf-8"
)
HEADER = (ROOT / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrDisplayPlugin.h").read_text(
    encoding="utf-8"
)
CONTEXT = (ROOT / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrContext.cpp").read_text(
    encoding="utf-8"
)
INPUT = (ROOT / "android/vr/pico/apps/picoInterface/openxr/src/OpenXrInputPlugin.cpp").read_text(
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

    def test_swapchain_enumeration_rejects_empty_or_changed_counts(self):
        choose_start = SOURCE.index("static int64_t chooseSwapChainFormat")
        choose_end = SOURCE.index("bool OpenXrDisplayPlugin::initSwapChains", choose_start)
        choose = SOURCE[choose_start:choose_end]
        self.assertIn("formatCount == 0", choose)
        self.assertIn("uint32_t populatedFormatCount { 0 };", choose)
        self.assertIn("populatedFormatCount != formatCount", choose)
        init_end = SOURCE.index("void OpenXrDisplayPlugin::destroySwapChains", choose_end)
        init = SOURCE[choose_end:init_end]
        self.assertIn("if (format == -1)", init)
        self.assertIn("imageCount == 0", init)
        self.assertIn("populatedImageCount != imageCount", init)
        self.assertLess(init.index("populatedImageCount != imageCount"), init.index("_images[i] = std::move(images)"))

    def test_partial_swapchain_initialization_is_cleaned_up(self):
        self.assertIn("void destroySwapChains();", HEADER)
        self.assertIn("auto failInitialization = [&]", SOURCE)
        self.assertGreaterEqual(SOURCE.count("return failInitialization();"), 5)
        destroy_start = SOURCE.index("void OpenXrDisplayPlugin::destroySwapChains()")
        destroy_end = SOURCE.index("bool OpenXrDisplayPlugin::initLayers", destroy_start)
        destroy = SOURCE[destroy_start:destroy_end]
        self.assertIn("xrDestroyFoveationProfileFB", destroy)
        self.assertIn("xrDestroySwapchain(swapchain)", destroy)
        self.assertIn("swapchain = XR_NULL_HANDLE", destroy)
        uncustomize = SOURCE.index("void OpenXrDisplayPlugin::uncustomizeContext()")
        self.assertIn("destroySwapChains();", SOURCE[uncustomize:uncustomize + 300])

    def test_periodic_latency_traces_are_opt_in(self):
        self.assertIn('"debug.overte.latency_trace"', CONTEXT)
        self.assertIn("_picoLatencyTraceEnabled = requested ==", CONTEXT)
        display_guard = SOURCE.index("if (_context->_picoLatencyTraceEnabled)")
        display_clock = SOURCE.index("usecTimestampNow()", display_guard)
        display_log = SOURCE.index("PICO_LATENCY_XR_FRAME", display_clock)
        self.assertLess(display_guard, display_clock)
        self.assertLess(display_clock, display_log)
        input_guard = INPUT.index("if (_context->_picoLatencyTraceEnabled)")
        input_clock = INPUT.index("usecTimestampNow()", input_guard)
        input_log = INPUT.index("PICO_LATENCY_INPUT", input_clock)
        self.assertLess(input_guard, input_clock)
        self.assertLess(input_clock, input_log)

    def test_instance_loss_does_not_reprocess_the_same_event(self):
        start = CONTEXT.index("bool OpenXrContext::pollEvents()")
        end = CONTEXT.index("bool OpenXrContext::beginFrame()", start)
        poll = CONTEXT[start:end]
        loss_start = poll.index("XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING")
        loss_end = poll.index("case XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED", loss_start)
        loss = poll[loss_start:loss_end]
        self.assertIn("_shouldRunFrameCycle = false;", loss)
        self.assertIn("break;", loss)
        self.assertNotIn("continue;", loss)
        self.assertIn("event = { .type = XR_TYPE_EVENT_DATA_BUFFER };", poll)

    def test_render_loop_honors_event_poll_failure(self):
        start = SOURCE.index("bool OpenXrDisplayPlugin::beginFrameRender")
        end = SOURCE.index("void OpenXrDisplayPlugin::submitFrame", start)
        render = SOURCE[start:end]
        self.assertIn("if (!_context->pollEvents())", render)
        self.assertIn("deactivate();", render)
        self.assertIn("return false;", render)

    def test_egl_config_requires_all_color_channels(self):
        start = CONTEXT.index("bool OpenXrContext::initSession()")
        end = CONTEXT.index("bool OpenXrContext::initSpaces()", start)
        session = CONTEXT[start:end]
        self.assertEqual(session.count("EGL_RED_SIZE, 8"), 2)
        self.assertEqual(session.count("EGL_GREEN_SIZE, 8"), 2)
        self.assertEqual(session.count("EGL_BLUE_SIZE, 8"), 2)

    def test_reference_spaces_are_capability_checked_and_transactional(self):
        start = CONTEXT.index("bool OpenXrContext::initSpaces()")
        end = CONTEXT.index("#define ENUM_TO_STR", start)
        spaces = CONTEXT[start:end]
        self.assertIn("spaceTypeCount == 0", spaces)
        self.assertIn("populatedSpaceTypeCount != spaceTypeCount", spaces)
        self.assertIn("XR_REFERENCE_SPACE_TYPE_STAGE", spaces)
        self.assertIn("XR_REFERENCE_SPACE_TYPE_VIEW", spaces)
        self.assertIn("XrSpace stageSpace { XR_NULL_HANDLE };", spaces)
        self.assertIn("XrSpace viewSpace { XR_NULL_HANDLE };", spaces)
        rollback = spaces.index("xrDestroySpace(stageSpace)")
        publish_stage = spaces.index("_stageSpace = stageSpace;")
        publish_view = spaces.index("_viewSpace = viewSpace;")
        self.assertLess(rollback, publish_stage)
        self.assertLess(publish_stage, publish_view)
        self.assertIn("_stageSpace != XR_NULL_HANDLE && _viewSpace != XR_NULL_HANDLE", spaces)

    def test_failed_space_initialization_rolls_back_session(self):
        start = CONTEXT.index("bool OpenXrContext::initPostGraphics()")
        body = CONTEXT[start:]
        create = body.index("if (!initSession())")
        space_failure = body.index("if (!initSpaces())", create)
        destroy = body.index("xrDestroySession(_session)", space_failure)
        clear = body.index("_session = XR_NULL_HANDLE", destroy)
        failed_return = body.index("return false;", clear)
        success = body.index("return true;", failed_return)
        self.assertLess(create, space_failure)
        self.assertLess(space_failure, destroy)
        self.assertLess(destroy, clear)
        self.assertLess(clear, failed_return)
        self.assertLess(failed_return, success)

    def test_session_transition_failures_disable_rendering(self):
        start = CONTEXT.index("bool OpenXrContext::updateSessionState")
        end = CONTEXT.index("bool OpenXrContext::pollEvents", start)
        transitions = CONTEXT[start:end]

        ready = transitions[transitions.index("XR_SESSION_STATE_READY"):
                            transitions.index("XR_SESSION_STATE_STOPPING")]
        self.assertLess(ready.index("_shouldRunFrameCycle = false"), ready.index("xrBeginSession"))
        begin_failure = ready.index('"Failed to begin session!"')
        self.assertIn("_isValid = false", ready[begin_failure:begin_failure + 180])

        stopping = transitions[transitions.index("XR_SESSION_STATE_STOPPING"):
                               transitions.index("XR_SESSION_STATE_LOSS_PENDING")]
        self.assertLess(stopping.index("_shouldRunFrameCycle = false"), stopping.index("xrEndSession"))
        end_failure = stopping.index('"Failed to end session!"')
        self.assertIn("_isValid = false", stopping[end_failure:end_failure + 180])

        loss = transitions[transitions.index("XR_SESSION_STATE_LOSS_PENDING"):]
        quit_state = loss.index("_shouldQuit = true")
        disable = loss.index("_shouldRunFrameCycle = false", quit_state)
        invalid = loss.index("_isValid = false", disable)
        stopped = loss.index("_isSessionRunning = false", invalid)
        self.assertLess(quit_state, disable)
        self.assertLess(disable, invalid)
        self.assertLess(invalid, stopped)
        self.assertNotIn("xrDestroySession", loss)
        self.assertNotIn("_session = XR_NULL_HANDLE", loss)
        self.assertIn("queued for ordered teardown", loss)

    def test_session_scoped_events_reject_stale_handles(self):
        start = CONTEXT.index("bool OpenXrContext::pollEvents()")
        end = CONTEXT.index("bool OpenXrContext::beginFrame()", start)
        poll = CONTEXT[start:end]
        cases = (
            ("XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED", "sessionStateChanged.session", "updateSessionState"),
            ("XR_TYPE_EVENT_DATA_INTERACTION_PROFILE_CHANGED", "interactionProfileChanged.session",
             "xrGetCurrentInteractionProfile"),
            ("XR_TYPE_EVENT_DATA_USER_PRESENCE_CHANGED_EXT", "eventdata.session", "_hmdMounted ="),
        )
        for event_type, session_field, first_side_effect in cases:
            case = poll.index("case " + event_type)
            next_case = poll.find("case ", case + 5)
            body = poll[case:next_case if next_case >= 0 else len(poll)]
            null_check = body.index("_session == XR_NULL_HANDLE")
            identity_check = body.index(session_field + " != _session")
            stale_break = body.index("break;", identity_check)
            side_effect = body.index(first_side_effect, stale_break)
            self.assertLess(null_check, stale_break)
            self.assertLess(identity_check, stale_break)
            self.assertLess(stale_break, side_effect)

    def test_optional_debug_messenger_is_checked_and_destroyed(self):
        system_start = CONTEXT.index("bool OpenXrContext::initSystem()")
        extension_walk = CONTEXT.index(
            "auto next = reinterpret_cast<const XrExtensionProperties*>", system_start)
        system = CONTEXT[system_start:extension_walk]
        self.assertIn('loadXrFunction(', system)
        self.assertIn('"xrCreateDebugUtilsMessengerEXT"', system)
        self.assertIn('"xrDestroyDebugUtilsMessengerEXT"', system)
        self.assertIn("XrDebugUtilsMessengerEXT candidate { XR_NULL_HANDLE }", system)
        create = system.index("xrCreateDebugUtilsMessengerEXT(", system.index("if (debugFunctionsLoaded)"))
        check = system.index('"Failed to create OpenXR debug messenger"', create)
        publish = system.index("_debugMessenger = candidate", check)
        self.assertLess(create, check)
        self.assertLess(check, publish)

        destructor = CONTEXT[CONTEXT.index("OpenXrContext::~OpenXrContext()"):
                             CONTEXT.index("bool OpenXrContext::initInstance()")]
        destroy = destructor.index("xrDestroyDebugUtilsMessengerEXT(_debugMessenger)")
        instance = destructor.index("xrDestroyInstance(_instance)")
        self.assertLess(destroy, instance)
        self.assertIn("_debugMessenger = XR_NULL_HANDLE", destructor[destroy:instance])

    def test_refresh_rate_capability_and_enumeration_fail_closed(self):
        start = CONTEXT.index("if (_displayRefreshRateSupported)")
        end = CONTEXT.index("return true;", start)
        refresh = CONTEXT[start:end]
        self.assertIn("const bool functionsLoaded", refresh)
        failure = refresh.index("if (!functionsLoaded)")
        self.assertIn("_displayRefreshRateSupported = false", refresh[failure:])
        self.assertIn("xrEnumerateDisplayRefreshRatesFB = nullptr", refresh[failure:])
        self.assertIn("xrGetDisplayRefreshRateFB = nullptr", refresh[failure:])
        self.assertIn("xrRequestDisplayRefreshRateFB = nullptr", refresh[failure:])
        self.assertIn("rateCount > 0", refresh)
        self.assertIn("uint32_t populatedRateCount { 0 }", refresh)
        self.assertIn("populatedRateCount == rateCount", refresh)
        finite = refresh.index("std::isfinite(rate)")
        positive = refresh.index("rate > 0.0f", finite)
        request = refresh.index("xrRequestDisplayRefreshRateFB(_session", positive)
        self.assertLess(finite, positive)
        self.assertLess(positive, request)

    def test_end_frame_failure_invalidates_render_cycle(self):
        start = SOURCE.index("bool OpenXrDisplayPlugin::endFrame")
        end = SOURCE.index("void OpenXrDisplayPlugin::postPreview", start)
        body = SOURCE[start:end]
        call = body.index("xrEndFrame")
        failure = body.index('"failed to end frame!"', call)
        disable = body.index("_context->_shouldRunFrameCycle = false", failure)
        invalidate = body.index("_context->_isValid = false", disable)
        failed_return = body.index("return false;", invalidate)
        self.assertLess(call, failure)
        self.assertLess(failure, disable)
        self.assertLess(disable, invalidate)
        self.assertLess(invalidate, failed_return)

    def test_frame_wait_and_begin_failures_invalidate_render_cycle(self):
        present_start = SOURCE.index("void OpenXrDisplayPlugin::hmdPresent()")
        present_end = SOURCE.index("bool OpenXrDisplayPlugin::endFrame", present_start)
        present = SOURCE[present_start:present_end]
        wait = present.index("xrWaitFrame")
        wait_failure = present.index('"xrWaitFrame failed"', wait)
        wait_disable = present.index("_context->_shouldRunFrameCycle = false", wait_failure)
        wait_invalidate = present.index("_context->_isValid = false", wait_disable)
        wait_return = present.index("return;", wait_invalidate)
        self.assertLess(wait_failure, wait_disable)
        self.assertLess(wait_disable, wait_invalidate)
        self.assertLess(wait_invalidate, wait_return)

        begin_start = CONTEXT.index("bool OpenXrContext::beginFrame()")
        begin_end = CONTEXT.index("bool OpenXrContext::initPreGraphics()", begin_start)
        begin = CONTEXT[begin_start:begin_end]
        call = begin.index("xrBeginFrame")
        failure = begin.index('"failed to begin frame!"', call)
        disable = begin.index("_shouldRunFrameCycle = false", failure)
        invalidate = begin.index("_isValid = false", disable)
        failed_return = begin.index("return false;", invalidate)
        self.assertLess(failure, disable)
        self.assertLess(disable, invalidate)
        self.assertLess(invalidate, failed_return)

    def test_context_destroys_spaces_and_session_before_instance(self):
        start = CONTEXT.index("OpenXrContext::~OpenXrContext()")
        end = CONTEXT.index("bool OpenXrContext::initInstance()", start)
        cleanup = CONTEXT[start:end]
        session_guard = cleanup.index("_session != XR_NULL_HANDLE")
        view_destroy = cleanup.index("xrDestroySpace(_viewSpace)", session_guard)
        stage_destroy = cleanup.index("xrDestroySpace(_stageSpace)", view_destroy)
        session_destroy = cleanup.index("xrDestroySession(_session)", stage_destroy)
        clear_view = cleanup.index("_viewSpace = XR_NULL_HANDLE", session_destroy)
        clear_stage = cleanup.index("_stageSpace = XR_NULL_HANDLE", clear_view)
        clear_session = cleanup.index("_session = XR_NULL_HANDLE", clear_stage)
        debug_destroy = cleanup.index("xrDestroyDebugUtilsMessengerEXT", clear_session)
        instance_destroy = cleanup.index("xrDestroyInstance(_instance)", debug_destroy)
        self.assertLess(view_destroy, stage_destroy)
        self.assertLess(stage_destroy, session_destroy)
        self.assertLess(session_destroy, clear_view)
        self.assertLess(clear_view, clear_stage)
        self.assertLess(clear_stage, clear_session)
        self.assertLess(clear_session, debug_destroy)
        self.assertLess(debug_destroy, instance_destroy)
        self.assertIn("_isSessionRunning = false", cleanup)
        self.assertIn("_shouldRunFrameCycle = false", cleanup)

    def test_display_destructor_has_idempotent_swapchain_fallback(self):
        start = SOURCE.index("OpenXrDisplayPlugin::~OpenXrDisplayPlugin()")
        end = SOURCE.index("bool OpenXrDisplayPlugin::isSupported", start)
        destructor = SOURCE[start:end]
        self.assertIn("destroySwapChains();", destructor)
        self.assertIn("~OpenXrDisplayPlugin() override", HEADER)

        destroy_start = SOURCE.index("void OpenXrDisplayPlugin::destroySwapChains()")
        destroy_end = SOURCE.index("bool OpenXrDisplayPlugin::initLayers", destroy_start)
        destroy = SOURCE[destroy_start:destroy_end]
        self.assertIn("_foveationProfile != XR_NULL_HANDLE", destroy)
        self.assertIn("_foveationProfile = XR_NULL_HANDLE", destroy)
        self.assertIn("swapchain != XR_NULL_HANDLE", destroy)
        self.assertIn("swapchain = XR_NULL_HANDLE", destroy)


if __name__ == "__main__":
    unittest.main()
