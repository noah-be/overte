#!/usr/bin/env python3
"""Source-level regression checks for the Pico WebView JNI frame bridge.

These checks intentionally run without Android or Qt. They protect the two
bridge invariants that previously caused blank pages or unsafe image copies.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
CPP = ROOT / "android/apps/picoInterface/src/PicoWebViewItem.cpp"
JAVA = ROOT / "android/apps/picoInterface/src/main/java/org/overte/pico/OffscreenWebView.java"


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
        self.assertIn("catch (RuntimeException exception)", body)
        self.assertNotIn("new WebView(PicoInterfaceActivity.getInstance())", body)

    def test_jni_bridge_uses_java_initialized_global_class(self):
        activity = (ROOT / "android/apps/picoInterface/src/main/java/org/overte/pico/PicoInterfaceActivity.java").read_text(
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


if __name__ == "__main__":
    unittest.main()
