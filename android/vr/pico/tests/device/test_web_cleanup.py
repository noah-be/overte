#!/usr/bin/env python3
"""Original WebView cleanup methods; Android effects/faults are test boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'


class WebCleanupTest(unittest.TestCase):
    def test_original_cleanup_continues_after_each_effect_failure(self):
        source = (JAVA / 'OffscreenWebView.java').read_text()
        methods = source[source.index('    public static void destroyAll()'):
                         source.index('    public static void load(')]
        driver = '''package org.overte.pico;
import java.util.*;
public class WebCleanupTestDriver {
    static final Map<Long, Instance> INSTANCES = new LinkedHashMap<>();
    static final List<String> events = new ArrayList<>();
    static final Main MAIN = new Main();
    static String fail;
    static boolean memory;
    static int warnings;
    enum Event { REDACTED }
    static class RedactingDiagnostics {
        static void w(Event value) { ++warnings; }
        static void i(Event value) {}
    }
    static class Looper {
        static final Looper MAIN = new Looper();
        static Looper myLooper() { return MAIN; }
        static Looper getMainLooper() { return MAIN; }
    }
    static void effect(String name) {
        events.add(name);
        if (name.equals(fail)) {
            if (memory) throw new OutOfMemoryError("synthetic-only");
            throw new IllegalStateException("synthetic-only");
        }
    }
    static class Main {
        void post(Runnable run) { run.run(); }
        void removeCallbacks(Runnable run) { effect("remove"); }
    }
    static class View {
        void stopLoading() { effect("stop"); }
        void loadUrl(String url) { effect("blank"); }
        void destroy() { effect("destroy"); }
        void clearFocus() { effect("focus"); }
    }
    static class Instance {
        boolean active = true;
        float pendingScroll = 3;
        View view = new View();
        Runnable renderFrame = () -> {};
        void cancelActiveTouch() { effect("touch"); }
        void disposeGraphics() { effect("graphics"); }
    }
    static void releaseTextFocus(Instance instance) { effect("editor"); }
''' + methods + '''
    static void need(boolean value) { if (!value) throw new AssertionError(events.toString()); }
    public static void main(String[] args) {
        List<String> expected = Arrays.asList("editor","remove","touch","graphics","stop","blank","destroy");
        for (boolean oom : new boolean[]{false, true}) {
            memory = oom;
            for (String fault : expected) {
                events.clear(); warnings = 0; fail = fault;
                Instance first = new Instance(), second = new Instance();
                INSTANCES.put(1L, first); INSTANCES.put(2L, second);
                destroyAll();
                need(INSTANCES.isEmpty() && !first.active && !second.active);
                List<String> both = new ArrayList<>(expected); both.addAll(expected);
                need(events.equals(both) && warnings == 2);
            }
            for (String fault : Arrays.asList("touch", "editor", "focus")) {
                events.clear(); warnings = 0; fail = fault;
                Instance first = new Instance(), second = new Instance();
                INSTANCES.put(1L, first); INSTANCES.put(2L, second);
                cancelAllInput();
                need(first.pendingScroll == 0 && second.pendingScroll == 0);
                need(events.equals(Arrays.asList("touch","editor","focus","touch","editor","focus")));
                need(warnings == 2 && first.active && second.active);
                INSTANCES.clear();
            }
        }
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='pico-web-cleanup-') as scratch:
            path = Path(scratch) / 'WebCleanupTestDriver.java'
            path.write_text(driver)
            subprocess.run(['javac', '-d', scratch, str(path)], check=True, timeout=20)
            result = subprocess.run(['java', '-cp', scratch, 'org.overte.pico.WebCleanupTestDriver'],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main(verbosity=2)
