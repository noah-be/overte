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


if __name__ == "__main__":
    unittest.main()
