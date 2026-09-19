#!/usr/bin/env python3
"""Native Android editor operations with test InputConnection, not a VR keyboard run."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / 'android/vr/pico/apps/picoInterface'
JAVA = APP / 'src/main/java/org/overte/pico'
HERE = Path(__file__).parent
class TextInputTest(unittest.TestCase):
    def test_actual_android_editor_operations(self):
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        jar = sdk / 'platforms/android-26/android.jar'
        with tempfile.TemporaryDirectory(prefix='pico-text-') as scratch:
            subprocess.run(['javac', '-encoding', 'UTF-8', '-cp', str(jar), '-d', scratch,
                str(JAVA / 'PicoTextInput.java'), str(HERE / 'java/org/overte/pico/PicoTextInputTest.java')],
                check=True, timeout=30)
            subprocess.run(['java', '-cp', scratch + os.pathsep + str(jar), 'org.overte.pico.PicoTextInputTest'],
                check=True, timeout=30)
    def test_qt_and_android_focus_boundaries_are_real_callers(self):
        cpp = (APP / 'src/PicoWebViewItem.cpp').read_text()
        for hook in ('keyPressEvent', 'inputMethodEvent', 'inputMethodQuery', 'focusInEvent', 'focusOutEvent'):
            self.assertIn('PicoWebViewItem::' + hook, cpp)
        self.assertIn('forceActiveFocus(Qt::MouseFocusReason)', cpp)
        self.assertIn('hasActiveFocus() && isVisible() && isEnabled()', cpp)
        self.assertIn('event->replacementStart() || event->replacementLength()', cpp)
        self.assertIn('reinterpret_cast<const jchar*>(text.utf16())', cpp)
        java = (JAVA / 'OffscreenWebView.java').read_text()
        self.assertIn('textFocus != instance || !instance.active || !instance.view.hasFocus()', java)
        self.assertIn('!activity.hasWindowFocus()', java)
        self.assertIn('PicoTextInput.text(focusedEditor(instance), text, composing)', java)
        self.assertIn('PicoTextInput.key(focusedEditor(instance), key)', java)
        self.assertIn('releaseTextFocus(old)', java)
        self.assertIn('releaseTextFocus(instance)', java[java.index('public static void load('):])
        text = (JAVA / 'PicoTextInput.java').read_text()
        self.assertNotIn('evaluateJavascript', text)
        self.assertNotIn('Log.', text)
        self.assertNotIn('Normalizer', text)
if __name__ == '__main__': unittest.main(verbosity=2)
