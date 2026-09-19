#!/usr/bin/env python3
"""Execute production URL policy and compile complete WebView caller against API 26."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'
HERE = Path(__file__).parent

class NativeWebPolicyTest(unittest.TestCase):
    def test_policy_and_actual_android_caller_compile(self):
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        with tempfile.TemporaryDirectory(prefix='pico-native-web-') as scratch:
            subprocess.run(['javac', '-encoding', 'UTF-8', '-d', scratch,
                str(JAVA / 'PicoRestartUrlPolicy.java'), str(JAVA / 'PicoWebUrlPolicy.java'),
                str(HERE / 'java/org/overte/pico/PicoWebUrlPolicyTest.java')], check=True, timeout=30)
            subprocess.run(['java', '-cp', scratch, 'org.overte.pico.PicoWebUrlPolicyTest'],
                check=True, timeout=30)
            subprocess.run(['javac', '-encoding', 'UTF-8', '-cp',
                str(sdk / 'platforms/android-26/android.jar'), '-d', scratch,
                *[str(JAVA / name) for name in ('PicoRestartUrlPolicy.java', 'PicoWebUrlPolicy.java',
                    'PicoTouchState.java', 'PicoWebInputGate.java', 'OffscreenWebView.java', 'RedactingDiagnostics.java', 'PicoTextInput.java')],
                str(ROOT / 'security/redaction/java/org/overte/security/SafeDiagnostics.java'),
                str(HERE / 'java-stubs/org/overte/pico/PicoInterfaceActivity.java')],
                check=True, timeout=30)

    def test_every_browser_entry_boundary_is_enforced(self):
        source = (JAVA / 'OffscreenWebView.java').read_text()
        self.assertEqual(2, source.count('PicoWebUrlPolicy.navigation(url)'))
        self.assertIn('PicoWebUrlPolicy.resource(request.getUrl().toString())', source)
        self.assertIn('PicoWebUrlPolicy.navigation(request.getUrl().toString())', source)
        for setting in ('setAllowFileAccess', 'setAllowContentAccess',
                        'setAllowFileAccessFromFileURLs', 'setAllowUniversalAccessFromFileURLs'):
            self.assertIn(setting + '(false)', source)
            self.assertNotIn(setting + '(true)', source)
        self.assertIn('handler.cancel()', source)
        self.assertIn('request.deny()', source)
        self.assertNotIn('addJavascriptInterface', source)
        self.assertIn('current.view == source', source)

if __name__ == '__main__':
    unittest.main(verbosity=2)
