#!/usr/bin/env python3
"""Original queued WebView input entry methods, test-only Android/render boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'


class WebInputQueueTest(unittest.TestCase):
    def test_original_input_entries_reject_old_foreground_and_owner(self):
        source = (JAVA / 'OffscreenWebView.java').read_text()
        registry = next(line for line in source.splitlines()
                        if 'private static final Map<Long, Instance> INSTANCES =' in line)
        self.assertIn('new ConcurrentHashMap<>()', registry)
        def between(start, end):
            return source[source.index(start):source.index(end, source.index(start))]
        helpers = ''
        if '    static void setInputForeground(' in source:
            helpers = between('    static void setInputForeground(', '    private static void failCurrentInstance(')
        else:
            # Baseline has no production ingress gate: keep the Android lifecycle
            # boundary observable so ORIGINAL pointer/focus/text/scroll expose RED.
            helpers = '''static void setInputForeground(PicoInterfaceActivity owner, boolean active) {
                if (owner == PicoInterfaceActivity.current) INPUT_GATE.update(owner, active);
                if (!active) cancelAllInput();
            }'''
        methods = between('    public static void pointer(', '    private static void releaseTextFocus(')
        methods += between('    public static void focus(', '    private static final class Instance')
        driver = '''package org.overte.pico;
import java.util.*;
import java.lang.reflect.Field;
import java.lang.ref.WeakReference;
import java.util.concurrent.ConcurrentHashMap;
public class WebInputQueueDriver {
    static final PicoWebInputGate INPUT_GATE = new PicoWebInputGate();
''' + registry + '''
    static final List<Runnable> queue = new ArrayList<>();
    static Instance textFocus;
    static int pointers, edits, keys, scrolls, focusRequests, cancelled;
    enum Event { CALLBACK_DISCARDED }
    static class RedactingDiagnostics { static void w(Event event) {} }
    static class PicoInterfaceActivity {
        static PicoInterfaceActivity current;
        boolean focused = true;
        static PicoInterfaceActivity getInstance() { return current; }
        boolean hasWindowFocus() { return focused; }
    }
    interface InstanceCommand { void run(Instance instance); }
    // Queue/instance lookup is the explicit Android scheduler boundary. Every
    // public input method and the production ingress gate below are original.
    static void postCommand(long handle, String name, InstanceCommand command) {
        queue.add(() -> { Instance value = INSTANCES.get(handle); if (value != null) command.run(value); });
    }
    static void drain() { List<Runnable> copy = new ArrayList<>(queue); queue.clear(); copy.forEach(Runnable::run); }
    static void cancelAllInput() { ++cancelled; textFocus = null; }
    static void releaseTextFocus(Instance instance) { if (textFocus == instance) textFocus = null; }
    static void failCurrentInstance(long handle, Instance instance, String name, Throwable error) { throw new AssertionError(error); }
    static class EditorInfo {}
    interface InputConnection {}
    static class PicoTextInput {
        static boolean valid(String value) { return value != null; }
        static boolean text(InputConnection input, String text, boolean composing) { if (input != null) ++edits; return input != null; }
        static boolean key(InputConnection input, int key) { if (input != null) ++keys; return input != null; }
    }
    interface Callback { void complete(String value); }
    static class View {
        final PicoInterfaceActivity owner;
        View(PicoInterfaceActivity value) { owner = value; }
        Object getContext() { return owner; }
        boolean hasFocus() { return true; }
        boolean requestFocus() { ++focusRequests; return true; }
        InputConnection onCreateInputConnection(EditorInfo info) { return new InputConnection() {}; }
        void evaluateJavascript(String script, Callback callback) { ++scrolls; callback.complete(""); }
    }
    static class Instance {
        boolean active = true;
        float pendingScroll;
        final View view;
        Instance(PicoInterfaceActivity owner) { view = new View(owner); }
        void dispatchPointer(int action, float x, float y) { ++pointers; }
        void refreshLayout() {}
    }
''' + helpers + methods + '''
    static void need(boolean value) { if (!value) throw new AssertionError("stale queued input executed"); }
    static void inputs() {
        pointer(1, 0, 1, 1); focus(1, true); editText(1, "test", false); editKey(1, 1); scroll(1, 1, 1, 1);
    }
    static int total() { return pointers + edits + keys + scrolls + focusRequests; }
    public static void main(String[] args) throws Exception {
        PicoInterfaceActivity first = new PicoInterfaceActivity();
        PicoInterfaceActivity.current = first;
        INSTANCES.put(1L, new Instance(first));
        setInputForeground(first, true);
        inputs(); drain(); need(total() == 5);
        // The Activity/foreground epoch is unchanged when a WebView is replaced.
        // Commands admitted for the old instance must not target its successor.
        int incarnationBefore = total();
        Thread producer = new Thread(() -> inputs()); producer.start(); producer.join();
        INSTANCES.put(1L, new Instance(first));
        drain(); need(total() == incarnationBefore);
        inputs(); drain(); need(total() == incarnationBefore + 5); // fresh successor input works
        incarnationBefore = total();
        INSTANCES.remove(1L); inputs();
        INSTANCES.put(1L, new Instance(first));
        drain(); need(total() == incarnationBefore); // no live target at admission
        int before = total(); inputs(); setInputForeground(first, false); drain(); need(total() == before);
        // Even a rapid resume must not revalidate pre-pause input.
        setInputForeground(first, true); inputs(); setInputForeground(first, false);
        setInputForeground(first, true); drain(); need(total() == before);
        // Input queued while paused never becomes fresh after resume.
        setInputForeground(first, false); inputs(); setInputForeground(first, true); drain(); need(total() == before);
        inputs(); setInputForeground(first, true); drain(); need(total() == before + 5); // duplicate allow
        before = total(); inputs();
        PicoInterfaceActivity replacement = new PicoInterfaceActivity();
        PicoInterfaceActivity.current = replacement;
        INSTANCES.put(1L, new Instance(replacement)); // Reused handle across Activity replacement.
        setInputForeground(replacement, true); drain(); need(total() == before);
        setInputForeground(first, false); inputs(); drain(); need(total() == before + 5); // stale owner cannot veto
        before = total(); inputs(); replacement.focused = false; drain(); need(total() == before);
        replacement.focused = true;
        INSTANCES.put(1L, new Instance(first)); inputs(); drain(); need(total() == before); // foreign view context
        INSTANCES.put(1L, new Instance(replacement));
        Field generation = PicoWebInputGate.class.getDeclaredField("generation"); generation.setAccessible(true);
        generation.setLong(INPUT_GATE, Long.MAX_VALUE - 1);
        setInputForeground(replacement, false); setInputForeground(replacement, true);
        inputs(); drain(); need(total() == before); // exhaustion is permanently closed
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='pico-web-input-queue-') as scratch:
            path = Path(scratch) / 'WebInputQueueDriver.java'
            path.write_text(driver)
            subprocess.run(['javac', '-d', scratch, str(path), str(JAVA / 'PicoWebInputGate.java')], check=True, timeout=20)
            result = subprocess.run(['java', '-cp', scratch, 'org.overte.pico.WebInputQueueDriver'],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main(verbosity=2)
