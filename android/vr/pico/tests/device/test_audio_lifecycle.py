#!/usr/bin/env python3
"""Real JNI Shared gate and bounded cleanup helper; no device audio execution."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / 'android/vr/pico/apps/picoInterface'
JAVA = APP / 'src/main/java/org/overte/pico'
HERE = Path(__file__).parent

class AudioLifecycleTest(unittest.TestCase):
    def test_native_gate_and_bounded_shutdown(self):
        jdk = Path(shutil.which('javac')).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='pico-sh006-') as scratch:
            def run(*args):
                subprocess.run(list(map(str, args)), check=True, timeout=30)
            library = Path(scratch) / 'libpico-audio-gate.so'
            run('c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread', '-shared', '-fPIC',
                '-I' + str(jdk / 'include'), '-I' + str(jdk / 'include/linux'),
                APP / 'audio/PicoAudioLifecycle.cpp', '-o', library)
            run('javac', '-d', scratch, JAVA / 'PicoAudioLifecycle.java', JAVA / 'PicoAudioShutdown.java',
                HERE / 'java/org/overte/pico/PicoAudioLifecycleTest.java')
            run('java', '-cp', scratch, 'org.overte.pico.PicoAudioLifecycleTest', library)
            executable = Path(scratch) / 'gate'
            run('c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                ROOT / 'tests/device/contracts/audio/lifecycle-gate-test.cpp', '-o', executable)
            run(executable)

    def test_actual_capture_and_activity_bindings(self):
        source = (JAVA / 'AndroidAudioInput.java').read_text()
        capture = source[source.index('private static void captureLoop'):]
        self.assertEqual(2, capture.count('PicoAudioLifecycle.mayCapture()'))
        self.assertEqual(2, capture.count('PicoAudioLifecycle.revoke()'))
        self.assertIn('if (!PicoAudioLifecycle.begin(true)) return false', source)
        self.assertIn('if (!SHUTDOWN.ready())', source)
        self.assertNotIn('resumeRequest', source)
        self.assertIn('public static synchronized void setMuted(boolean value)', source)
        self.assertIn('private static native void nativePolicyChanged(boolean captureAllowed)', source)
        activity = (JAVA / 'PicoInterfaceActivity.java').read_text()
        self.assertIn('AndroidAudioInput.setForeground(resumed && focused)', activity)
        self.assertIn('AndroidAudioInput.setForeground(false)', activity)

if __name__ == '__main__': unittest.main(verbosity=2)
