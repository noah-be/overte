#!/usr/bin/env python3
"""Source regression guards only: these do not execute UIKit or WebKit."""
import json
from pathlib import Path
import re
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


if __name__ == "__main__":
    unittest.main()
