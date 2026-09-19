#!/usr/bin/env python3
"""Execute original Activity teardown/helper with only Android effect boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'


class ActivityTeardownTest(unittest.TestCase):
    def test_original_destroy_preserves_replacement_and_completes_cleanup(self):
        source = (JAVA / 'PicoInterfaceActivity.java').read_text()
        destroy = 'protected void onDestroy()' + source.split('protected void onDestroy()', 1)[1].split(
            '    private static void runShutdownStep', 1)[0]
        helper = 'private static void runShutdownStep' + source.split(
            'private static void runShutdownStep', 1)[1].split('    @SuppressLint', 1)[0]
        focus = 'public void onWindowFocusChanged(' + source.split(
            'public void onWindowFocusChanged(', 1)[1].split('\n    }', 1)[0] + '\n    }\n'
        lifecycle = source[source.index('    public void onResume()'):source.index('    @Override\n    public void onWindowFocusChanged')]
        web_source = (JAVA / 'OffscreenWebView.java').read_text()
        ingress = web_source[web_source.index('    static void setInputForeground('):web_source.index('    private static void postInputCommand(')]
        driver = '''package org.overte.pico;
public final class PicoActivityTeardownTest {
    static int web, audio, xr, qt, errors, cancelled;
    static boolean failWeb, failAudio, failInput, audioAllowed;
    enum Event { REDACTED }
    static class RedactingDiagnostics { static void e(Event event) { ++errors; } }
    static class OffscreenWebView {
        static final PicoWebInputGate INPUT_GATE = new PicoWebInputGate();
        static void destroyAll() { ++web; if (failWeb) throw new IllegalStateException("test-only"); }
        static void cancelAllInput() { ++cancelled; if (failInput) throw new OutOfMemoryError("test-only"); }
''' + ingress + '''
    }
    static class AndroidAudioInput {
        static void setForeground(boolean active) {
            audioAllowed = active;
            ++audio; if (failAudio) throw new OutOfMemoryError("test-only");
        }
    }
    // Native observer ownership is exercised with its actual Java/JNI in the
    // separate visibility test. This boundary does not claim an OS teardown.
    static class PicoClientVisibility {
        static void detach(Object owner) {}
        static void foreground(Object owner, boolean active) {}
    }
    static class QtBoundary {
        protected void onDestroy() { ++qt; }
        public void onResume() {}
        public void onPause() {}
        public void onWindowFocusChanged(boolean focused) {}
    }
    static class PicoInterfaceActivity extends QtBoundary {
        boolean resumed, focused = true;
        boolean hasWindowFocus() { return focused; }
        static PicoInterfaceActivity getInstance() { return INSTANCE.current(); }
        static final PicoActivityInstancePolicy<PicoInterfaceActivity> INSTANCE = new PicoActivityInstancePolicy<>();
        void releaseOpenXRActivity() { ++xr; }
''' + destroy + helper + focus + lifecycle + '''
    }
    static void need(boolean condition) { if (!condition) throw new AssertionError(); }
    public static void main(String[] args) {
        PicoInterfaceActivity first = new PicoInterfaceActivity();
        PicoInterfaceActivity replacement = new PicoInterfaceActivity();
        PicoInterfaceActivity.INSTANCE.register(first);
        PicoInterfaceActivity.INSTANCE.register(replacement);
        first.onWindowFocusChanged(false);
        need(audio == 0 && cancelled == 0);
        replacement.onWindowFocusChanged(false);
        need(audio == 1 && cancelled == 1);
        audio = 0;
        first.onDestroy();
        need(PicoInterfaceActivity.INSTANCE.current() == replacement);
        need(web == 0 && audio == 0 && xr == 1 && qt == 1);
        replacement.onDestroy();
        need(PicoInterfaceActivity.INSTANCE.current() == null);
        need(web == 1 && audio == 1 && xr == 2 && qt == 2);
        failWeb = true; failAudio = true; failInput = true;
        PicoInterfaceActivity failing = new PicoInterfaceActivity();
        PicoInterfaceActivity.INSTANCE.register(failing);
        failing.onDestroy();
        need(web == 2 && audio == 2 && xr == 3 && qt == 3 && errors == 3);
        need(PicoInterfaceActivity.INSTANCE.current() == null);
        failWeb = false; failAudio = false; failInput = false;
        PicoInterfaceActivity current = new PicoInterfaceActivity();
        PicoInterfaceActivity.INSTANCE.register(current);
        current.onResume();
        PicoWebInputGate gate = OffscreenWebView.INPUT_GATE;
        PicoWebInputGate.Ticket ticket = gate.capture();
        need(gate.permits(ticket, current) && audioAllowed);
        current.onPause(); // Window focus can still be true at pause.
        need(gate.capture() == null && !audioAllowed);
        current.onResume();
        need(!gate.permits(ticket, current) && gate.capture() != null);
        current.onWindowFocusChanged(false);
        need(gate.capture() == null && !audioAllowed);
        current.onWindowFocusChanged(true);
        need(gate.capture() != null && audioAllowed);
        current.onPause();
        current.onWindowFocusChanged(true); // Focus alone cannot override pause.
        need(gate.capture() == null && !audioAllowed);
        current.onResume();
        ticket = gate.capture();
        first.onPause(); first.onResume(); first.onWindowFocusChanged(false);
        need(gate.permits(ticket, current)); // Obsolete owner cannot change ingress.
        current.onDestroy();
        need(gate.capture() == null);
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='pico-activity-teardown-') as scratch:
            scratch = Path(scratch)
            test = scratch / 'PicoActivityTeardownTest.java'
            test.write_text(driver)
            subprocess.run(['javac', '-d', str(scratch), str(test), str(JAVA / 'PicoActivityInstancePolicy.java'),
                str(JAVA / 'PicoWebInputGate.java')],
                check=True, timeout=20)
            result = subprocess.run(['java', '-cp', str(scratch), 'org.overte.pico.PicoActivityTeardownTest'],
                capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main(verbosity=2)
