"""Execute actual launcher and keyboard methods with explicit Android effect seams."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'


def method(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class ActivityIngressTest(unittest.TestCase):
    def run_java(self, driver):
        with tempfile.TemporaryDirectory(prefix='pico-ingress-') as scratch:
            path = Path(scratch)
            (path / 'IngressTest.java').write_text(driver)
            subprocess.run(['javac', '-d', scratch, str(path / 'IngressTest.java'),
                            str(JAVA / 'PicoActivityInstancePolicy.java'), str(JAVA / 'PicoKeyboardPolicy.java')],
                           check=True, timeout=20)
            subprocess.run(['java', '-cp', scratch, 'org.overte.pico.IngressTest'], check=True, timeout=5)

    def test_permission_delivery_after_cancel_or_destroy_cannot_relaunch(self):
        source = (JAVA / 'PermissionsActivity.java').read_text()
        methods = '\n'.join(method(source, signature) for signature in [
            'public void onRequestPermissionsResult(', 'private void launchInterface()'])
        self.run_java('''package org.overte.pico;
public class IngressTest {
    static class Intent { Intent(Object context, Class<?> target) {} }
    static class PicoInterfaceActivity {}
    static class AndroidBoundary {
        boolean finishing, destroyed;
        int launches;
        boolean isFinishing() { return finishing; }
        boolean isDestroyed() { return destroyed; }
        void startActivity(Intent intent) { ++launches; }
        void finish() { finishing = true; }
        public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {}
    }
    static class Launcher extends AndroidBoundary {
        static final int RECORD_AUDIO_REQUEST = 20;
        boolean interfaceLaunched;
''' + methods + '''
    }
    static void need(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) {
        for (int grant : new int[]{0, -1}) {
            Launcher cancelled = new Launcher(); cancelled.finishing = true;
            cancelled.onRequestPermissionsResult(20, new String[]{"microphone"}, new int[]{grant});
            need(cancelled.launches == 0 && !cancelled.interfaceLaunched);
            Launcher destroyed = new Launcher(); destroyed.destroyed = true;
            destroyed.onRequestPermissionsResult(20, new String[]{"microphone"}, new int[]{grant});
            need(destroyed.launches == 0 && !destroyed.interfaceLaunched);
            Launcher current = new Launcher();
            current.onRequestPermissionsResult(99, new String[]{}, new int[]{});
            need(current.launches == 0);
            current.onRequestPermissionsResult(20, new String[]{"microphone"}, new int[]{grant});
            current.onRequestPermissionsResult(20, new String[]{}, new int[]{});
            need(current.launches == 1 && current.interfaceLaunched);
        }
    }
}
''')

    def test_keyboard_ingress_requires_current_resumed_focused_activity(self):
        source = (JAVA / 'PicoInterfaceActivity.java').read_text()
        dispatch = method(source, 'public boolean dispatchKeyEvent(')
        self.run_java('''package org.overte.pico;
public class IngressTest {
    static class InputDevice {
        static final int KEYBOARD_TYPE_ALPHABETIC = 2, SOURCE_KEYBOARD = 1, SOURCE_GAMEPAD = 2, SOURCE_JOYSTICK = 4;
        boolean external = true;
        int type = KEYBOARD_TYPE_ALPHABETIC;
        boolean isExternal() { return external; }
        int getKeyboardType() { return type; }
    }
    static class KeyEvent {
        InputDevice device = new InputDevice();
        int source = InputDevice.SOURCE_KEYBOARD;
        InputDevice getDevice() { return device; }
        boolean isFromSource(int value) { return (source & value) == value; }
    }
    static class QtBoundary {
        int forwarded;
        public boolean dispatchKeyEvent(KeyEvent event) { ++forwarded; return false; }
    }
    static class Activity extends QtBoundary {
        static final PicoActivityInstancePolicy<Activity> INSTANCE = new PicoActivityInstancePolicy<>();
        boolean resumed, focused = true;
        boolean hasWindowFocus() { return focused; }
''' + dispatch + '''
    }
    static void need(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) {
        KeyEvent key = new KeyEvent();
        Activity owner = new Activity(); Activity.INSTANCE.register(owner);
        need(owner.dispatchKeyEvent(key) && owner.forwarded == 0); // Focus may precede resume.
        owner.resumed = true;
        need(!owner.dispatchKeyEvent(key) && owner.forwarded == 1);
        owner.focused = false;
        need(owner.dispatchKeyEvent(key) && owner.forwarded == 1);
        owner.focused = true; owner.resumed = false;
        need(owner.dispatchKeyEvent(key) && owner.forwarded == 1); // Pause before focus loss.
        owner.resumed = true;
        Activity replacement = new Activity(); replacement.resumed = true;
        Activity.INSTANCE.register(replacement);
        need(owner.dispatchKeyEvent(key) && owner.forwarded == 1);
        need(!replacement.dispatchKeyEvent(key) && replacement.forwarded == 1);
        key.source |= InputDevice.SOURCE_GAMEPAD;
        need(replacement.dispatchKeyEvent(key) && replacement.forwarded == 1);
        key.source = InputDevice.SOURCE_KEYBOARD; key.device = null;
        need(replacement.dispatchKeyEvent(key) && replacement.forwarded == 1);
        Activity.INSTANCE.clear(replacement);
        need(replacement.dispatchKeyEvent(key) && replacement.forwarded == 1);
    }
}
''')


if __name__ == '__main__':
    unittest.main()
