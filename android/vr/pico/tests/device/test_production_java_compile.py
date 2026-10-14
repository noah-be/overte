#!/usr/bin/env python3
"""Compile every production Pico Java caller using SDK 36 and explicit dependency stubs.

This is a focused javac check, not a Gradle build or Android execution.
"""
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'
HERE = Path(__file__).parent

class ProductionJavaCompileTest(unittest.TestCase):
    def test_all_production_pico_java_sources_compile(self):
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        stubs = [HERE / 'java-stubs' / name for name in (
            'org/qtproject/qt5/android/bindings/QtActivity.java',
            'io/highfidelity/utils/HifiUtils.java', 'org/overte/pico/R.java',
            'org/overte/web/EmbeddedWebView.java',
            'org/overte/documents/DocumentAdapter.java', 'org/overte/snapshot/SnapshotAdapter.java')]
        with tempfile.TemporaryDirectory(prefix='pico-production-javac-') as scratch:
            subprocess.run(['javac', '-encoding', 'UTF-8', '-cp',
                str(sdk / 'platforms/android-36/android.jar'), '-d', scratch,
                *map(str, sorted(JAVA.glob('*.java'))), *map(str, stubs),
                str(ROOT / 'android/common/web/java/org/overte/web/EmbeddedWebHost.java'),
                str(ROOT / 'android/common/web/java/org/overte/web/WebFilePickerState.java'),
                str(ROOT / 'security/redaction/java/org/overte/security/SafeDiagnostics.java'),
                str(ROOT / 'android/common/documents/java/org/overte/documents/DocumentHost.java'),
                str(ROOT / 'android/common/snapshot/java/org/overte/snapshot/SnapshotHost.java')],
                check=True, timeout=60)
            # Inspect actual SDK-compiled bytecode, rather than source strings.
            descriptors = subprocess.check_output(['javap', '-private', '-s', '-classpath', scratch,
                'org.overte.pico.OffscreenWebView'], text=True)
            for method, signature in (
                ('nativeLifecycle', '(JJZ)V'), ('nativeFrame', '(JJLjava/nio/ByteBuffer;II)V'),
                ('setVisible', '(JZ)V')):
                line = descriptors.index(method + '(')
                actual = descriptors[line:].split('descriptor:', 1)[1].splitlines()[0].strip()
                self.assertEqual(actual, signature, method)

            activity = subprocess.check_output(['javap', '-private', '-c', '-classpath', scratch,
                'org.overte.pico.PicoInterfaceActivity'], text=True)
            # Inspect the real SDK-compiled callback/lambda callgraph. Runtime
            # callback sequences are also executed by test_activity_teardown.
            blocks = re.split(r'\n(?=  (?:public|private|protected) )', activity)
            frame_calls = [block for block in blocks if
                'Method org/overte/pico/OffscreenWebView.setForeground:' in block]
            self.assertEqual(len(frame_calls), 4, activity)  # create/resume/pause/destroy
            for callback, active in (('onCreate', 0), ('onResume', 1), ('onPause', 0), ('onDestroy', 0)):
                matches = [block for block in frame_calls if 'lambda$' + callback + '$' in block]
                self.assertEqual(len(matches), 1, callback)
                self.assertRegex(matches[0], r'iconst_' + str(active) +
                    r'\s+\d+: invokestatic[^\n]+OffscreenWebView\.setForeground:')
            focus_blocks = [block for block in blocks if 'onWindowFocusChanged(' in
                block.splitlines()[0] or 'lambda$onWindowFocusChanged$' in block.splitlines()[0]]
            self.assertTrue(focus_blocks)
            self.assertFalse(any('OffscreenWebView.setForeground:' in block for block in focus_blocks))
            self.assertTrue(any('OffscreenWebView.setInputForeground:' in block for block in focus_blocks))

if __name__ == '__main__':
    unittest.main(verbosity=2)
