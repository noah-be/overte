#!/usr/bin/env python3
"""Contracts for Pico-specific native glue that cannot execute off-device."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "android/vr/pico/apps/picoInterface"
ANDROID_COMMON = ROOT / "android/common"
CMAKE = (APP / "CMakeLists.txt").read_text(encoding="utf-8")
PROVIDER = (APP / "openxr/src/OpenXrProvider.cpp").read_text(encoding="utf-8")
GL_CANVAS = (ANDROID_COMMON / "src/OffscreenGLCanvas.cpp").read_text(encoding="utf-8")
QT_INPUT = (ANDROID_COMMON / "src/QtInputConnectionCompat.cpp").read_text(encoding="utf-8")


class PicoPlatformGlueTests(unittest.TestCase):
    def test_openxr_provider_publishes_only_supported_plugins(self):
        for getter, plugin in (("getDisplayPlugins", "OpenXrDisplayPlugin"),
                               ("getInputPlugins", "OpenXrInputPlugin")):
            body = re.search(rf"{getter}\(\) override \{{(.*?)\n    \}}", PROVIDER, re.DOTALL)
            self.assertIsNotNone(body)
            self.assertIn(f"std::make_shared<{plugin}>(context)", body.group(1))
            self.assertIn("if (plugin->isSupported())", body.group(1))
            self.assertLess(body.group(1).index("isSupported"), body.group(1).index("push_back"))

    def test_display_and_input_share_one_openxr_context(self):
        self.assertEqual(PROVIDER.count("std::make_shared<OpenXrContext>()"), 1)
        self.assertEqual(PROVIDER.count("(context)"), 2)
        self.assertIn("destroyInputPlugins() override { _inputPlugins.clear(); }", PROVIDER)
        self.assertIn("destroyDisplayPlugins() override { _displayPlugins.clear(); }", PROVIDER)

    def test_android_gl_context_initializes_gl_before_reporting(self):
        make_current = re.search(r"bool OffscreenGLCanvas::makeCurrent\(\) \{(.*?)\n\}",
                                 GL_CANVAS, re.DOTALL)
        self.assertIsNotNone(make_current)
        body = make_current.group(1)
        self.assertIn("if (result)", body)
        self.assertLess(body.index("gl::initModuleGl()"), body.index("LOG_GL_CONTEXT_INFO"))

    def test_qt_input_compat_exports_both_expected_jni_symbols(self):
        for symbol in ("finishComposingText", "updateCursorPosition"):
            self.assertIn(
                f"Java_org_qtproject_qt5_android_QtNativeInputConnection_{symbol}", QT_INPUT
            )
        self.assertEqual(QT_INPUT.count("return JNI_TRUE;"), 2)

    def test_cmake_replaces_upstream_sources_and_links_openxr(self):
        for source in ("PicoWebViewItem", "Application_Setup"):
            self.assertIn(f'{source}\\\\.', CMAKE)
        self.assertIn('../../../../common/src/OffscreenGLCanvas.cpp', CMAKE)
        self.assertIn('../../../../common/src/QtInputConnectionCompat.cpp', CMAKE)
        self.assertIn("target_link_libraries(openxr picoOpenXR)", CMAKE)
        self.assertIn("add_dependencies(${TARGET_NAME} openxr)", CMAKE)


if __name__ == "__main__":
    unittest.main()
