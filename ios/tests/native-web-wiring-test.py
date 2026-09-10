#!/usr/bin/env python3
"""Source regression guards only: these do not execute UIKit or WebKit."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Wiring(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "ios/web/ContainedWebView.mm").read_text()

    def test_actual_target_and_startup(self):
        cmake = (ROOT / "ios/integration/CMakeLists.txt").read_text()
        for path in ("../web/NativeWebAdapter.cpp", "../web/ContainedWebView.mm"):
            self.assertIn(path, cmake)
        self.assertIn('target_link_libraries(Overte "-framework WebKit")', cmake)
        self.assertIn("Q_COREAPP_STARTUP_FUNCTION(installContainedWeb)", self.source)
        self.assertIn("overte::web::installNativeWebAdapter(&nativeAdapter())", self.source)

    def test_arc_reaches_target_in_other_cmake_directory(self):
        source = (ROOT / "ios/integration/CMakeLists.txt").read_text()
        properties = "\n".join(re.findall(r'set_source_files_properties\([\s\S]*?\)', source))
        properties = properties.replace("${CMAKE_CURRENT_LIST_DIR}", str(ROOT / "ios/integration"))
        checks = "\n".join(
            f'get_source_file_property(arc "{ROOT / "ios" / name}" TARGET_DIRECTORY Overte COMPILE_OPTIONS)\n'
            'if(NOT arc STREQUAL "-fobjc-arc")\nmessage(FATAL_ERROR "ARC not visible to Overte")\nendif()'
            for name in ("src/SecureAccountStore.mm", "src/RedactingDiagnostics.mm",
                         "audio/AVAudioSessionAdapter.mm", "web/ContainedWebView.mm"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "interface").mkdir()
            (root / "integration").mkdir()
            (root / "interface/CMakeLists.txt").write_text('add_library(Overte INTERFACE)\n')
            (root / "integration/CMakeLists.txt").write_text(properties + "\n")
            (root / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.24)\nproject(ArcScope LANGUAGES NONE)\n'
                'add_subdirectory(interface)\nadd_subdirectory(integration)\n' + checks)
            result = subprocess.run(["cmake", "-S", str(root), "-B", str(root / "build")],
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Reproduce the real failure: the same properties set only in the
            # integration directory must not satisfy the consuming target.
            (root / "integration/CMakeLists.txt").write_text(properties.replace("TARGET_DIRECTORY Overte", "") + "\n")
            result = subprocess.run(["cmake", "-S", str(root), "-B", str(root / "before-build")],
                                    text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ARC not visible to Overte", result.stdout + result.stderr)

    def test_constant_rules(self):
        definition = self.source.split("NSString* const CONTENT_RULES =", 1)[1].split(";", 1)[0]
        strings = re.findall(r'@?("(?:[^"\\]|\\.)*")', definition)
        rules = json.loads("".join(json.loads(value) for value in strings))
        self.assertEqual(rules[0]["trigger"]["load-type"], ["third-party"])
        self.assertEqual(rules[0]["action"]["type"], "block")
        self.assertEqual(set(rules[1]["trigger"]["resource-type"]), {"script", "media", "raw", "popup"})
        self.assertNotIn("example.org", definition)

    def test_response_and_native_denial_guards(self):
        for text in ("[WKWebsiteDataStore nonPersistentDataStore]",
                     "allowsContentJavaScript = NO", "acceptsNativeWebMime(",
                     "WKPermissionDecisionDeny", "NSUrlSessionAuthChallengeCancelAuthenticationChallenge".replace("NSUrl", "NSURL"),
                     "NSUrlRequestUseProtocolCachePolicy".replace("NSUrl", "NSURL"),
                     "if (@available(iOS 18.4, *))", "completionHandler(nil)",
                     "self.presentation.viewIfLoaded.window ?: self.presenter.viewIfLoaded.window"):
            self.assertIn(text, self.source)
        for forbidden in ("evaluateJavaScript:", "openURL:", "credentialForTrust:",
                          "NSLog(", "localizedDescription", "addScriptMessageHandler:"):
            self.assertNotIn(forbidden, self.source)

    def test_ambiguous_scene_and_subframe_rejection(self):
        selector = self.source.split("UIViewController* foregroundPresenter(", 1)[1].split("\n}\n}", 1)[0]
        self.assertIn("*selectedWindow = nil;", selector)
        self.assertIn("if (candidate) { return nil; }", selector)
        self.assertEqual(selector.count("return presenter;"), 1)
        self.assertLess(selector.index("candidate = window;"), selector.index("candidate.rootViewController"))
        self.assertIn("view == self.webView && action.targetFrame.mainFrame", self.source)


if __name__ == "__main__":
    unittest.main()
