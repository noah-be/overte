#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute original legacy Java lifecycle/frame methods; Android effects are explicit boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / "android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico"


class LegacyWebLifecycleTest(unittest.TestCase):
    def test_original_methods_fence_frames_and_pause_only_the_owned_page(self):
        source = (JAVA / "OffscreenWebView.java").read_text()

        def between(start, end):
            return source[source.index(start):source.index(end, source.index(start))]

        methods = between("    private static synchronized long frameEpoch()", "    private OffscreenWebView()")
        methods += between("    private static void postCommand(", "    private static void postInputCommand(")
        methods += between("    private static void failCurrentInstance(", "    @SuppressLint(")
        methods += between("    public static void destroy(", "    public static void pointer(")
        instance = source[source.index("    private static final class Instance {"):].rsplit("\n}", 1)[0]
        driver = r'''package org.overte.pico;
import java.util.*;
import java.lang.ref.WeakReference;
import java.util.concurrent.ConcurrentHashMap;
import java.nio.ByteBuffer;
public class LegacyWebLifecycleDriver {
    static final Map<Long, Instance> INSTANCES = new ConcurrentHashMap<>();
    static final PicoWebInputGate INPUT_GATE = new PicoWebInputGate(), FRAME_GATE = new PicoWebInputGate();
    static final Main MAIN = new Main();
    static final int FRAME_INTERVAL_MS = 100, MAX_TEXTURE_EDGE = 2048;
    static Instance textFocus;
    static long nextFrameEpoch = 1;
    interface InstanceCommand { void run(Instance instance); }
    static int frames, creationFailures;
    static final List<String> effects = new ArrayList<>();
    enum Event { REDACTED }
    static class RedactingDiagnostics {
        static void e(Event value) {} static void w(Event value) {} static void i(Event value) {}
    }
    static class PicoInterfaceActivity {
        static PicoInterfaceActivity current;
        static PicoInterfaceActivity getInstance() { return current; }
        boolean focused = true;
        boolean hasWindowFocus() { return focused; }
    }
    static class PicoWebUrlPolicy {
        static String navigation(String value) { return value; } // URL policy has its own actual tests.
    }
    static class Looper {
        static final Looper MAIN = new Looper();
        static Looper myLooper() { return MAIN; } static Looper getMainLooper() { return MAIN; }
    }
    static class Main {
        final List<Runnable> commands = new ArrayList<>(), timers = new ArrayList<>();
        boolean rejectFrames;
        boolean post(Runnable callback) { commands.add(callback); return true; }
        boolean postDelayed(Runnable callback, long delay) {
            if (rejectFrames) return false;
            timers.add(callback); return true;
        }
        void removeCallbacks(Runnable callback) { commands.remove(callback); timers.remove(callback); }
        void drain() {
            List<Runnable> copy = new ArrayList<>(commands); commands.clear(); copy.forEach(Runnable::run);
        }
    }
    interface JavascriptCallback { void complete(String result); }
    static class WebView {
        final PicoInterfaceActivity owner;
        int pauses, resumes, draws, mediaPauses, destroys, loads;
        boolean mediaPlaying, editor;
        Runnable duringEditor;
        boolean hasFocus() { return true; }
        String url, fault;
        Runnable duringDraw;
        WebView(PicoInterfaceActivity owner) { this.owner = owner; }
        Object getContext() { return owner; }
        void onPause() { ++pauses; effects.add("pause"); if ("pause".equals(fault)) throw new IllegalStateException(); }
        void onResume() { ++resumes; effects.add("resume"); }
        void evaluateJavascript(String script, JavascriptCallback callback) {
            ++mediaPauses; mediaPlaying = false; effects.add("media");
            if ("media".equals(fault)) throw new IllegalStateException();
            if (callback != null) callback.complete("");
        }
        void pauseTimers() { throw new AssertionError("global WebView timer pause is forbidden"); }
        void draw(Canvas canvas) { ++draws; if (duringDraw != null) duringDraw.run(); }
        int getScrollX() { return 0; } int getScrollY() { return 0; }
        int getWidth() { return 32; } int getHeight() { return 32; }
        void clearFocus() {} void stopLoading() {} void destroy() { ++destroys; }
        void loadUrl(String value) { url = value; ++loads; }
        WebView getSettings() { return this; }
        void setBackgroundColor(int value) {} void setUserAgentString(String value) {}
        void forceLayout() {} void invalidate() {} void measure(int width, int height) {} void layout(int a,int b,int c,int d) {}
        void dispatchGenericMotionEvent(MotionEvent event) {} void dispatchTouchEvent(MotionEvent event) {}
    }
    // This frame/lifecycle harness replaces Android editor detection only.
    // The separate API test executes PicoWebEditorState against real Android APIs.
    static class PicoWebEditorState {
        static final PicoWebEditorState INACTIVE = new PicoWebEditorState();
        final boolean focused, numeric=false, password=false;
        PicoWebEditorState() { this(false); }
        PicoWebEditorState(boolean value) { focused=value; }
        static PicoWebEditorState inspect(WebView view, boolean admitted) {
            if (view.duringEditor != null) view.duringEditor.run();
            return admitted && view.editor ? new PicoWebEditorState(true) : INACTIVE;
        }
        boolean same(PicoWebEditorState other) { return focused == other.focused; }
    }
    static boolean publishedEditor;
    static long editorEpoch, editorRevision;
    static void nativeEditorState(long h,long e,long r,boolean f,boolean n,boolean p) {
        publishedEditor=f; editorEpoch=e; editorRevision=r;
    }
    static class View {
        static class MeasureSpec { static final int EXACTLY = 1; static int makeMeasureSpec(int size,int mode) { return size; } }
    }
    static class InputDevice { static final int SOURCE_MOUSE=1, SOURCE_TOUCHSCREEN=2; }
    static class MotionEvent {
        static final int ACTION_DOWN=0, ACTION_CANCEL=3, ACTION_HOVER_MOVE=7, ACTION_HOVER_ENTER=9, ACTION_HOVER_EXIT=10;
        static MotionEvent obtain(long down,long now,int action,float x,float y,int meta) { return new MotionEvent(); }
        void setSource(int source) {} void recycle() {}
    }
    static class Color { static final int WHITE=1, TRANSPARENT=0; }
    static class Bitmap {
        enum Config { ARGB_8888 }
        int width,height; boolean recycled;
        static Bitmap createBitmap(int width,int height,Config config) { Bitmap value=new Bitmap(); value.width=width; value.height=height; return value; }
        int getWidth() { return width; } int getHeight() { return height; }
        boolean isRecycled() { return recycled; } void recycle() { recycled=true; }
        void eraseColor(int color) {} void copyPixelsToBuffer(ByteBuffer output) {}
    }
    static class Canvas {
        Canvas(Bitmap bitmap) {} int save() { return 1; }
        void translate(float x,float y) {} void restoreToCount(int count) {} void scale(float x,float y) {}
    }
    static void nativeCreationFinished(long handle, boolean created) { if (!created) ++creationFailures; }
    static void nativeLifecycle(long handle,long epoch,boolean rendering) { effects.add("native:"+handle+":"+epoch+":"+rendering); }
    static void nativeFrame(long handle,long epoch,ByteBuffer pixels,int width,int height) { ++frames; }
    static void releaseTextFocus(Instance instance) { if (textFocus == instance) textFocus = null; }
''' + methods + instance + r'''
    static void need(boolean value, String reason) { if (!value) throw new AssertionError(reason + " " + effects); }
    static Instance add(long handle, PicoInterfaceActivity owner) {
        Instance value = new Instance(handle, new WebView(owner), 1);
        need(value.resize(32,32), "frame allocation failed");
        value.pendingUrl = "data:text/html,<video></video>";
        INSTANCES.put(handle,value); return value;
    }
    static void show(Instance value) { setVisible(value.nativeHandle,true); MAIN.drain(); }
    public static void main(String[] args) {
        PicoInterfaceActivity first = new PicoInterfaceActivity(); PicoInterfaceActivity.current = first;
        setForeground(first,true); MAIN.drain();
        Instance page = add(1, first), sibling = add(2, first);
        need(!page.rendering && MAIN.timers.isEmpty() && page.view.loads == 0, "dormant creation ran a hidden page");
        show(page); show(sibling);
        need(page.rendering && page.view.resumes == 1 && page.view.loads == 1, "initial show failed");
        page.view.mediaPlaying = sibling.view.mediaPlaying = true;
        Runnable oldFrame = page.pendingFrame;
        oldFrame.run(); need(frames == 1 && page.view.draws == 1, "positive frame missing");
        // Controlled provider metadata; the ORIGINAL production caller checks
        // input, frame, owner and current document admission before publishing.
        setInputForeground(first,true); textFocus=page; page.view.editor=true;
        page.publishEditorState();
        need(publishedEditor && editorEpoch==page.epoch && editorRevision>0,"admitted editor metadata missing");
        page.view.duringEditor = () -> setInputForeground(first,false);
        page.publishEditorState();
        need(!publishedEditor,"input revoked during metadata observation but published active");
        page.view.duringEditor=null;
        setInputForeground(first,true); textFocus=page;
        page.view.duringEditor=() -> { page.stopRendering(); page.updateRendering(); };
        page.publishEditorState();
        need(!publishedEditor,"document replaced during metadata observation but old state published");
        page.view.duringEditor=null; page.publishEditorState();
        need(publishedEditor,"fresh document editor did not recover");
        // DOM/editor focus changes only cancel input; a playing visible page continues.
        setInputForeground(first,false);
        page.pendingFrame.run(); need(frames == 2 && page.view.mediaPlaying, "keyboard focus incorrectly suspended media");
        Runnable retained = page.pendingFrame;
        int immediateBefore = frames;
        setVisible(1,false); setVisible(1,true);
        retained.run(); need(frames == immediateBefore, "rapid hide/show revalidated a frame before UI cleanup");
        MAIN.drain();
        retained = page.pendingFrame;
        int siblingPauses = sibling.view.pauses;
        setVisible(1,false); MAIN.drain();
        need(!page.rendering && !page.view.mediaPlaying && page.pendingFrame == null, "hide did not stop frame/media work");
        need(sibling.rendering && sibling.view.mediaPlaying && sibling.view.pauses == siblingPauses, "hide paused another page");
        int before = frames; retained.run(); need(frames == before, "hidden callback published");
        show(page); retained.run(); need(frames == before, "old hide epoch became valid after show");
        page.pendingFrame.run(); need(frames == before+1 && page.view.loads == 1, "fresh show lost frame or reloaded page");
        int rasterBefore = frames;
        page.view.duringDraw = () -> { setVisible(1,false); setVisible(1,true); };
        page.pendingFrame.run(); need(frames == rasterBefore, "visibility changed during raster but frame published");
        page.view.duringDraw = null; MAIN.drain();
        page.pendingFrame.run(); need(frames == rasterBefore+1, "fresh raster after interruption missing");
        retained = page.pendingFrame; before = frames;
        setForeground(first,false); setForeground(first,true);
        retained.run(); need(frames == before, "rapid pause/resume revalidated queued frame");
        MAIN.drain(); retained.run(); need(frames == before, "old callback survived lifecycle cleanup");
        page.pendingFrame.run(); need(frames == before+1, "new lifecycle epoch did not render");
        setForeground(first,false); MAIN.drain(); before = frames;
        page.renderFrame.run(); need(frames == before && !page.rendering && !sibling.rendering, "background rendered");
        setForeground(first,true); MAIN.drain();
        // An old Activity cannot suspend the new owner's active surface.
        PicoInterfaceActivity successor = new PicoInterfaceActivity(); PicoInterfaceActivity.current = successor;
        Instance newPage = add(3, successor); setForeground(successor,true); MAIN.drain(); show(newPage);
        setForeground(first,false); MAIN.drain(); need(newPage.rendering, "stale Activity vetoed current owner");
        need(!page.active && !sibling.active && page.view.destroys == 1 && sibling.view.destroys == 1,
            "owner replacement retained old pages/media");
        before = frames; page.renderFrame.run(); need(frames == before, "old owner's callback rendered");
        // Queue admission is bound to a precise instance, even with a reused test handle.
        setVisible(3,false); Instance replacement = add(3, successor); MAIN.drain();
        need(replacement.view.pauses == 0 && !replacement.rendering, "queued old visibility reached replacement");
        show(replacement); retained = replacement.pendingFrame; before = frames;
        replacement.view.fault = "media"; destroy(3); MAIN.drain();
        need(!INSTANCES.containsKey(3L) && !replacement.active && replacement.view.destroys == 1, "media fault interrupted teardown");
        retained.run(); need(frames == before, "dead callback published");
        Instance failed = add(4, successor); MAIN.rejectFrames=true; show(failed);
        need(!INSTANCES.containsKey(4L) && failed.view.destroys == 1 && creationFailures > 0, "queue failure left active renderer");
        MAIN.rejectFrames=false;
        destroyAll(); need(INSTANCES.isEmpty(), "teardown leaked instances");
        System.out.println("PASS original Java frame/lifecycle/media calls; Android scheduler, Canvas and native effects are host boundaries");
    }
}
'''
        # SystemClock is an Android effect boundary; preserve the original calls.
        with tempfile.TemporaryDirectory(prefix="pico-legacy-lifecycle-") as temporary:
            stage = Path(temporary)
            clock = stage / "android/os/SystemClock.java"
            clock.parent.mkdir(parents=True)
            clock.write_text("package android.os; public class SystemClock { public static long uptimeMillis() { return 1; } }\n")
            file = stage / "LegacyWebLifecycleDriver.java"
            file.write_text(driver)
            subprocess.run(["javac", "-d", temporary, str(file), str(clock),
                            str(JAVA / "PicoWebInputGate.java"), str(JAVA / "PicoTouchState.java")], check=True, timeout=30)
            subprocess.run(["java", "-cp", temporary, "org.overte.pico.LegacyWebLifecycleDriver"], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
