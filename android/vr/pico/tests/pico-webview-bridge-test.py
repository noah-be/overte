#!/usr/bin/env python3
"""Source-level regression checks for the Pico WebView JNI frame bridge.

These checks intentionally run without Android or Qt. They protect the two
bridge invariants that previously caused blank pages or unsafe image copies.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[4]
CPP = ROOT / "android/vr/pico/apps/picoInterface/src/PicoWebViewItem.cpp"
JAVA = ROOT / "android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico/OffscreenWebView.java"


class PicoWebViewBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CPP.read_text(encoding="utf-8")
        cls.java_source = JAVA.read_text(encoding="utf-8")

    def test_frame_readiness_does_not_sample_content_alpha(self):
        frame_source = re.search(
            r"QString PicoWebViewItem::frameSource\(\) const \{(.*?)\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(frame_source)
        body = frame_source.group(1)
        self.assertIn("_image.isNull()", body)
        self.assertNotIn("qAlpha", body)
        self.assertNotIn("_image.pixel", body)

    def test_direct_buffer_capacity_is_validated_before_copy(self):
        self.assertIn("GetDirectBufferCapacity(buffer)", self.source)
        accept_frame = re.search(
            r"void PicoWebViewItem::acceptFrame\((.*?)\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(accept_frame)
        body = accept_frame.group(1)
        self.assertIn("byteCount <", body)
        self.assertIn("width <= 0", body)
        self.assertIn("height <= 0", body)
        self.assertIn("numeric_limits", body)

    def test_qt_pointer_translation_uses_enter_and_cancel_actions(self):
        self.assertRegex(self.source, r"hoverEnterEvent\([^)]*\) \{ sendPointer\(9,")
        self.assertRegex(
            self.source,
            re.compile(r"mouseUngrabEvent\(\).*?sendPointer\(3,", re.DOTALL),
        )

    def test_background_mode_reaches_android_webview(self):
        self.assertIn('callStatic("setUseBackground", "(JZ)V"', self.source)
        self.assertIn("useBackground ? Color.WHITE : Color.TRANSPARENT", self.java_source)

    def test_navigation_clears_transient_input_state(self):
        load = re.search(
            r"public static void load\(.*?\n    \}", self.java_source, re.DOTALL
        )
        self.assertIsNotNone(load)
        self.assertIn("instance.cancelActiveTouch()", load.group(0))
        self.assertIn("instance.pendingScroll = 0.0f", load.group(0))

    def test_touch_dispatch_rejects_malformed_sequences(self):
        dispatch = re.search(
            r"void dispatchPointer\(.*?\n        \}", self.java_source, re.DOTALL
        )
        self.assertIsNotNone(dispatch)
        body = dispatch.group(0)
        self.assertIn("action == MotionEvent.ACTION_DOWN && touchState.isActive()", body)
        self.assertIn("dispatchPointer(MotionEvent.ACTION_CANCEL", body)
        self.assertIn("action != MotionEvent.ACTION_DOWN && !touchState.isActive()", body)
        self.assertIn("return;", body)

    def test_creation_fails_closed_without_activity_or_webview_provider(self):
        create = re.search(
            r"public static void create\(.*?\n    \}", self.java_source, re.DOTALL
        )
        self.assertIsNotNone(create)
        body = create.group(0)
        self.assertIn("PicoInterfaceActivity activity = PicoInterfaceActivity.getInstance()", body)
        self.assertIn("if (activity == null)", body)
        self.assertIn("view = new WebView(activity)", body)
        self.assertIn("catch (RuntimeException | OutOfMemoryError exception)", body)
        self.assertNotIn("new WebView(PicoInterfaceActivity.getInstance())", body)

    def test_jni_bridge_uses_java_initialized_global_class(self):
        activity = (ROOT / "android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico/PicoInterfaceActivity.java").read_text(
            encoding="utf-8"
        )
        self.assertIn("OffscreenWebView.initializeNativeBridge();", activity)
        self.assertIn("private static native void nativeInitialize();", self.java_source)
        self.assertIn("OffscreenWebView_nativeInitialize", self.source)
        self.assertIn("environment->NewGlobalRef(inputClass)", self.source)
        self.assertIn("webViewClass.compare_exchange_strong", self.source)
        self.assertIn("webViewJavaVm.store(vm", self.source)
        self.assertNotIn("FindClass(", self.source)
        self.assertNotIn("overtePicoOpenXRJavaVm", self.source)

    def test_resize_is_transactional_and_releases_old_bitmap(self):
        resize = re.search(
            r"boolean resize\(.*?\n        \}", self.java_source, re.DOTALL
        )
        self.assertIsNotNone(resize)
        body = resize.group(0)
        allocation = body.index("newBitmap = Bitmap.createBitmap")
        measure = body.index("view.measure")
        layout = body.index("view.layout", measure)
        assignment = body.index("bitmap = newBitmap")
        self.assertLess(allocation, assignment)
        self.assertLess(allocation, measure)
        self.assertLess(measure, layout)
        self.assertLess(layout, assignment)
        self.assertIn("catch (RuntimeException | OutOfMemoryError exception)", body)
        self.assertIn("return false;", body)
        self.assertIn("oldBitmap.recycle();", body)
        self.assertIn("return true;", body)

    def test_creation_and_destruction_handle_frame_resources(self):
        self.assertIn("if (!instance.resize(width, height))", self.java_source)
        self.assertLess(
            self.java_source.index("if (!instance.resize(width, height))"),
            self.java_source.index("INSTANCES.put(nativeHandle, instance)"),
        )
        self.assertIn('runCleanupStep("dispose frame buffer", old::disposeGraphics)', self.java_source)
        self.assertIn("void disposeGraphics()", self.java_source)

    def test_creation_status_is_confirmed_asynchronously(self):
        self.assertIn("_webViewCreationPending", self.source)
        self.assertIn("_webViewCreationPending = callStatic(", self.source)
        self.assertNotIn("_webViewCreated = true;", self.source)
        self.assertIn("OffscreenWebView_nativeCreationFinished", self.source)
        self.assertIn("Qt::QueuedConnection", self.source)
        self.assertIn("nativeCreationFinished(nativeHandle, true);", self.java_source)
        self.assertGreaterEqual(
            self.java_source.count("nativeCreationFinished(nativeHandle, false);"), 3
        )
        self.assertIn("MAX_CREATION_RETRIES { 3 }", self.source)
        self.assertIn("QTimer::singleShot(1000, this", self.source)

    def test_creation_queue_rejection_completes_native_handshake(self):
        create = re.search(
            r"public static void create\(.*?\n    \}",
            self.java_source,
            re.DOTALL,
        )
        self.assertIsNotNone(create)
        body = create.group(0)
        outer_post = body.index("boolean posted = MAIN.post")
        first_frame = body.index("if (!MAIN.post(instance.renderFrame))", outer_post)
        first_cleanup = body.index("destroyOnMain(nativeHandle)", first_frame)
        first_failure = body.index("nativeCreationFinished(nativeHandle, false)", first_cleanup)
        outer_failure = body.index("if (!posted)", first_failure)
        outer_callback = body.index("nativeCreationFinished(nativeHandle, false)", outer_failure)
        self.assertLess(outer_post, first_frame)
        self.assertLess(first_frame, first_cleanup)
        self.assertLess(first_cleanup, first_failure)
        self.assertLess(first_failure, outer_failure)
        self.assertLess(outer_failure, outer_callback)

    def test_command_and_render_queue_rejection_retire_instance(self):
        command_start = self.java_source.index("private static void postCommand")
        command_end = self.java_source.index("private static void failCurrentInstance", command_start)
        command = self.java_source[command_start:command_end]
        self.assertIn("boolean posted = MAIN.post", command)
        rejection = command.index("if (!posted)")
        callback = command.index("nativeCreationFinished(nativeHandle, false)", rejection)
        self.assertLess(rejection, callback)

        render_start = self.java_source.index("final Runnable renderFrame")
        render_end = self.java_source.index("Instance(long nativeHandle", render_start)
        render = self.java_source[render_start:render_end]
        post = render.index("if (!MAIN.postDelayed(this, FRAME_INTERVAL_MS))")
        cleanup = render.index("destroyOnMain(nativeHandle)", post)
        failure = render.index("nativeCreationFinished(nativeHandle, false)", cleanup)
        self.assertLess(post, cleanup)
        self.assertLess(cleanup, failure)

    def test_synchronous_creation_failures_also_retry(self):
        create = re.search(
            r"void PicoWebViewItem::createWebView\(\) \{(.*?)\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(create)
        body = create.group(1)
        self.assertIn("if (!jni.env)", body)
        self.assertIn("if (!url || !agent)", body)
        self.assertIn("if (!_webViewCreationPending)", body)
        self.assertGreaterEqual(body.count("scheduleCreationRetry();"), 3)
        self.assertIn("void PicoWebViewItem::scheduleCreationRetry()", self.source)
        self.assertIn("_webViewCreated || _webViewCreationRetryScheduled ||", self.source)
        self.assertIn("_webViewCreationRetryScheduled = true;", self.source)
        self.assertIn("_webViewCreationRetryScheduled = false;", self.source)

    def test_scroll_completion_is_bound_to_current_instance(self):
        scroll = re.search(
            r"public static void scroll\(.*?\n    \}",
            self.java_source,
            re.DOTALL,
        )
        self.assertIsNotNone(scroll)
        body = scroll.group(0)
        callback = body.index("instance.view.evaluateJavascript")
        active = body.index("instance.active", callback)
        identity = body.index("INSTANCES.get(nativeHandle) == instance", active)
        refresh = body.index("instance.refreshLayout()", identity)
        self.assertLess(callback, active)
        self.assertLess(active, identity)
        self.assertLess(identity, refresh)

    def test_all_creation_configuration_failures_report_and_cleanup(self):
        create = re.search(
            r"public static void create\(.*?\n    \}",
            self.java_source,
            re.DOTALL,
        )
        self.assertIsNotNone(create)
        body = create.group(0)
        guarded = body.index("try {")
        constructor = body.index("view = new WebView(activity)", guarded)
        settings = body.index("view.getSettings()", constructor)
        resize = body.index("instance.resize(width, height)", settings)
        load = body.index("view.loadUrl", resize)
        success = body.index("nativeCreationFinished(nativeHandle, true)", load)
        failure_catch = body.index("catch (RuntimeException | OutOfMemoryError exception)", success)
        cleanup = body.index("destroyOnMain(nativeHandle)", failure_catch)
        failure = body.index("nativeCreationFinished(nativeHandle, false)", cleanup)
        self.assertLess(guarded, constructor)
        self.assertLess(constructor, settings)
        self.assertLess(settings, resize)
        self.assertLess(resize, load)
        self.assertLess(load, success)
        self.assertLess(success, failure_catch)
        self.assertLess(failure_catch, cleanup)
        self.assertLess(cleanup, failure)

    def test_frame_failure_cleans_up_and_reenters_creation_handshake(self):
        render_start = self.java_source.index("final Runnable renderFrame")
        render_end = self.java_source.index("Instance(long nativeHandle", render_start)
        render = self.java_source[render_start:render_end]
        draw = render.index("view.draw(canvas)")
        restore = render.index("finally {", draw)
        restore_call = render.index("canvas.restoreToCount(saveCount)", restore)
        failure_catch = render.index("catch (RuntimeException | OutOfMemoryError exception)", restore_call)
        cleanup = render.index("destroyOnMain(nativeHandle)", failure_catch)
        failure = render.index("nativeCreationFinished(nativeHandle, false)", cleanup)
        reschedule_guard = render.index("active && INSTANCES.get(nativeHandle) == Instance.this", failure)
        reschedule = render.index("MAIN.postDelayed(this, FRAME_INTERVAL_MS)", reschedule_guard)
        self.assertLess(draw, restore)
        self.assertLess(restore, restore_call)
        self.assertLess(restore_call, failure_catch)
        self.assertLess(failure_catch, cleanup)
        self.assertLess(cleanup, failure)
        self.assertLess(failure, reschedule_guard)
        self.assertLess(reschedule_guard, reschedule)

    def test_destroy_cleanup_steps_are_exception_isolated(self):
        destroy_start = self.java_source.index("private static void destroyOnMain")
        destroy_end = self.java_source.index("public static void load", destroy_start)
        destroy = self.java_source[destroy_start:destroy_end]
        self.assertIn('runCleanupStep("cancel touch", old::cancelActiveTouch)', destroy)
        self.assertIn('runCleanupStep("dispose frame buffer", old::disposeGraphics)', destroy)
        self.assertIn('runCleanupStep("stop loading", old.view::stopLoading)', destroy)
        self.assertIn('runCleanupStep("clear page", () -> old.view.loadUrl("about:blank"))', destroy)
        self.assertIn('runCleanupStep("destroy view", old.view::destroy)', destroy)
        helper = destroy.index("private static void runCleanupStep")
        self.assertIn("catch (RuntimeException exception)", destroy[helper:])

    def test_async_commands_share_instance_bound_failure_recovery(self):
        helper_start = self.java_source.index("private static void postCommand")
        helper_end = self.java_source.index("@SuppressLint", helper_start)
        helpers = self.java_source[helper_start:helper_end]
        self.assertIn("catch (RuntimeException | OutOfMemoryError exception)", helpers)
        self.assertIn("failCurrentInstance(nativeHandle, instance, name, exception)", helpers)
        self.assertIn("INSTANCES.get(nativeHandle) != instance", helpers)
        cleanup = helpers.index("destroyOnMain(nativeHandle)")
        retry = helpers.index("nativeCreationFinished(nativeHandle, false)", cleanup)
        self.assertLess(cleanup, retry)
        for operation in [
            'postCommand(nativeHandle, "navigation"',
            'postCommand(nativeHandle, "background update"',
            'postCommand(nativeHandle, "User-Agent update"',
            'postCommand(nativeHandle, "resize"',
            'postCommand(nativeHandle, "pointer dispatch"',
            'postCommand(nativeHandle, "scroll dispatch"',
        ]:
            self.assertIn(operation, self.java_source)
        self.assertIn('nativeHandle, instance, "scroll layout", exception', self.java_source)

    def test_pending_properties_are_resynchronized_after_creation(self):
        result = re.search(
            r"void PicoWebViewItem::acceptCreationResult\(.*?\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(result)
        body = result.group(0)
        self.assertIn('callStatic("load"', body)
        self.assertIn('callStatic("setUserAgent"', body)
        self.assertIn('callStatic("setUseBackground"', body)
        self.assertIn('callStatic("resize"', body)
        self.assertIn("public static void setUserAgent", self.java_source)


if __name__ == "__main__":
    unittest.main()
