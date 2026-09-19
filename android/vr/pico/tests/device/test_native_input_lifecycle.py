#!/usr/bin/env python3
"""Focused source/focus routing and permission-revocation checks for production callers."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'
HERE = Path(__file__).parent

class NativeInputLifecycleTest(unittest.TestCase):
    def test_production_keyboard_and_audio_compile(self):
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        with tempfile.TemporaryDirectory(prefix='pico-input-lifecycle-') as scratch:
            subprocess.run(['javac', '-d', scratch, str(JAVA / 'PicoKeyboardPolicy.java'),
                str(HERE / 'java/org/overte/pico/PicoKeyboardPolicyTest.java')], check=True, timeout=30)
            subprocess.run(['java', '-cp', scratch, 'org.overte.pico.PicoKeyboardPolicyTest'],
                check=True, timeout=30)
            subprocess.run(['javac', '-cp', str(sdk / 'platforms/android-26/android.jar'),
                '-d', scratch, *[str(JAVA / name) for name in ('AndroidAudioInput.java',
                    'AndroidAudioInputPolicy.java', 'PicoAudioCaptureState.java', 'RedactingDiagnostics.java',
                    'PicoAudioLifecycle.java', 'PicoAudioShutdown.java')],
                str(ROOT / 'security/redaction/java/org/overte/security/SafeDiagnostics.java'),
                str(HERE / 'java-stubs/org/overte/pico/PicoInterfaceActivity.java')],
                check=True, timeout=30)

    def test_real_activity_uses_keyboard_policy_and_cancels_web_input(self):
        activity = (JAVA / 'PicoInterfaceActivity.java').read_text()
        self.assertIn('PicoKeyboardPolicy.forwardToQt(hasWindowFocus()', activity)
        self.assertIn('return super.dispatchKeyEvent(event)', activity)
        self.assertIn('OffscreenWebView.setInputForeground(this, resumed && focused)', activity)
        web = (JAVA / 'OffscreenWebView.java').read_text()
        self.assertIn('if (!active) cancelAllInput()', web)
        cancel = web[web.index('public static void cancelAllInput()'):web.index('private static void destroyOnMain')]
        self.assertIn('instance::cancelActiveTouch', cancel)
        self.assertIn('instance.pendingScroll = 0.0f', cancel)
        self.assertIn('runCleanupStep("clear view focus", instance.view::clearFocus)', cancel)

    def test_capture_rechecks_revocation_after_read_and_clears_buffer(self):
        source = (JAVA / 'AndroidAudioInput.java').read_text()
        self.assertIn('volatile AudioRecord recorder', source)
        capture = source[source.index('private static void captureLoop'):]
        read = capture.index('activeRecorder.read(')
        permission = capture.index('if (!microphonePermissionGranted()) { PicoAudioLifecycle.revoke(); publishPolicy(false); break; }', read)
        deliver = capture.index('nativeOnAudioData(audio, bytesRead)', read)
        self.assertLess(read, permission)
        self.assertLess(permission, deliver)
        self.assertIn('finally {\n            if (audio != null) java.util.Arrays.fill(audio, (byte) 0)', capture)

if __name__ == '__main__':
    unittest.main(verbosity=2)
