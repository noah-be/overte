package org.overte.pico;

import android.annotation.SuppressLint;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import org.overte.security.SafeDiagnostics.Event;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebChromeClient;
import android.webkit.PermissionRequest;
import android.webkit.GeolocationPermissions;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.SslErrorHandler;
import android.net.http.SslError;
import android.webkit.CookieManager;

import java.nio.ByteBuffer;
import java.io.ByteArrayInputStream;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/** Renders Android WebViews into buffers consumed by PicoWebViewItem. */
public final class OffscreenWebView {
    private static final String TAG = "OverteWebEntity";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    // Main-thread writes; input admission also reads from native/Qt threads.
    private static final Map<Long, Instance> INSTANCES = new ConcurrentHashMap<>();
    private static final PicoWebInputGate INPUT_GATE = new PicoWebInputGate();
    private static final PicoWebInputGate FRAME_GATE = new PicoWebInputGate();
    private static final int FRAME_INTERVAL_MS = 100;
    private static final int MAX_TEXTURE_EDGE = 2048;
    private static boolean wholeDocumentDrawEnabled;
    private static Instance textFocus;
    private static long nextFrameEpoch = 1;

    private static synchronized long frameEpoch() {
        if (nextFrameEpoch == 0) return 0;
        long value = nextFrameEpoch;
        nextFrameEpoch = value == Long.MAX_VALUE ? 0 : value + 1;
        return value;
    }

    private OffscreenWebView() { }

    public static void initializeNativeBridge() {
        nativeInitialize();
    }

    private static native void nativeInitialize();
    private static native void nativeCreationFinished(long nativeHandle, boolean created);
    private static native void nativeFrame(
        long nativeHandle, long epoch, ByteBuffer pixels, int width, int height);
    private static native void nativeLifecycle(long nativeHandle, long epoch, boolean rendering);
    private static native void nativeEditorState(
        long nativeHandle, long epoch, long revision, boolean focused, boolean numeric, boolean password);

    private interface InstanceCommand {
        void run(Instance instance);
    }

    private static void postCommand(long nativeHandle, String name, InstanceCommand command) {
        final Instance expected = INSTANCES.get(nativeHandle);
        if (expected == null) return;
        final WeakReference<Instance> target = new WeakReference<>(expected);
        boolean posted = MAIN.post(() -> {
            Instance instance = INSTANCES.get(nativeHandle);
            if (instance != target.get() || instance == null || !instance.active) {
                return;
            }
            try {
                command.run(instance);
            } catch (RuntimeException | OutOfMemoryError exception) {
                failCurrentInstance(nativeHandle, instance, name, exception);
            }
        });
        if (!posted) {
            RedactingDiagnostics.e(Event.REDACTED);
            nativeCreationFinished(nativeHandle, false);
        }
    }

    // Activity visibility is separate from the DOM/editor input focus gate.
    // update() fences already queued frames immediately, before Android cleanup.
    static void setForeground(PicoInterfaceActivity owner, boolean active) {
        if (PicoInterfaceActivity.getInstance() != owner) return;
        FRAME_GATE.update(owner, active);
        Runnable transition = () -> {
            if (PicoInterfaceActivity.getInstance() != owner) return;
            for (Instance instance : new ArrayList<>(INSTANCES.values())) {
                try {
                    if (instance.view.getContext() != owner) {
                        // A replacement Activity cannot keep the previous owner's
                        // hidden media/Views alive. Fresh Qt retry uses a new epoch.
                        destroyOnMain(instance.nativeHandle);
                        nativeCreationFinished(instance.nativeHandle, false);
                        continue;
                    }
                    if (!active) instance.suspend();
                    else instance.updateRendering();
                } catch (RuntimeException | OutOfMemoryError failure) {
                    failCurrentInstance(instance.nativeHandle, instance, "foreground lifecycle", failure);
                }
            }
        };
        if (Looper.myLooper() == Looper.getMainLooper()) transition.run();
        else if (!MAIN.post(transition)) RedactingDiagnostics.e(Event.REDACTED);
    }

    public static void setVisible(long nativeHandle, boolean visible) {
        Instance expected = INSTANCES.get(nativeHandle);
        if (expected == null || !expected.active) return;
        synchronized (expected) {
            if (expected.visible != visible) expected.visibilityRevision = frameEpoch();
            expected.visible = visible && expected.visibilityRevision > 0;
        }
        // Fence queued raster/input work at admission, not only when Android's
        // UI queue eventually applies the corresponding media transition.
        postCommand(nativeHandle, "surface visibility", instance -> {
            if (!visible) instance.suspend();
            else instance.updateRendering();
        });
    }

    static void setInputForeground(PicoInterfaceActivity owner, boolean active) {
        if (PicoInterfaceActivity.getInstance() != owner) return;
        INPUT_GATE.update(owner, active);
        // No gate monitor is held across Android cleanup.
        if (!active) cancelAllInput();
    }

    private static void postInputCommand(long handle, String name, InstanceCommand command) {
        final PicoWebInputGate.Ticket ticket = INPUT_GATE.capture();
        if (ticket == null) return;
        final Instance expected = INSTANCES.get(handle);
        if (expected == null) return;
        // A native handle can be reused within the same Activity generation.
        // Queued input belongs only to the instance present at admission; avoid
        // retaining a destroyed View/Activity merely because a callback is queued.
        final WeakReference<Instance> target = new WeakReference<>(expected);
        final long surfaceEpoch = expected.epoch;
        final long visibilityRevision = expected.visibilityRevision;
        postCommand(handle, name, instance -> {
            if (instance != target.get() || instance.epoch != surfaceEpoch
                    || instance.visibilityRevision != visibilityRevision || !instance.visible || !instance.rendering) return;
            PicoInterfaceActivity owner = PicoInterfaceActivity.getInstance();
            if (!INPUT_GATE.permits(ticket, owner) || !instance.active
                    || !owner.hasWindowFocus() || instance.view.getContext() != owner) return;
            command.run(instance);
        });
    }

    private static void failCurrentInstance(
            long nativeHandle, Instance instance, String operation, Throwable failure) {
        RedactingDiagnostics.e(Event.REDACTED);
        if (!instance.active || INSTANCES.get(nativeHandle) != instance) {
            return;
        }
        destroyOnMain(nativeHandle);
        nativeCreationFinished(nativeHandle, false);
    }

    @SuppressLint("SetJavaScriptEnabled")
    public static void create(long nativeHandle, int width, int height, String url,
                              String userAgent, boolean useBackground) {
        final String safeUrl = PicoWebUrlPolicy.navigation(url);
        if (safeUrl == null) {
            nativeCreationFinished(nativeHandle, false);
            return;
        }
        final PicoInterfaceActivity requestedOwner = PicoInterfaceActivity.getInstance();
        boolean posted = MAIN.post(() -> {
            WebView view = null;
            try {
                destroyOnMain(nativeHandle);
                PicoInterfaceActivity activity = PicoInterfaceActivity.getInstance();
                if (activity == null || activity != requestedOwner) {
                    RedactingDiagnostics.e(Event.REDACTED);
                    nativeCreationFinished(nativeHandle, false);
                    return;
                }
                boolean enableWholeDocumentDraw = !wholeDocumentDrawEnabled;
                if (enableWholeDocumentDraw) {
                    // This WebView has no ViewRoot and is rendered exclusively through
                    // draw(Canvas). Chromium otherwise retains only compositor tiles for
                    // its assumed on-screen viewport, leaving stale/blank areas after a
                    // scroll. Android requires enabling this before creating WebViews.
                    WebView.enableSlowWholeDocumentDraw();
                }
                view = new WebView(activity);
                if (enableWholeDocumentDraw) {
                    wholeDocumentDrawEnabled = true;
                }
                view.setBackgroundColor(useBackground ? Color.WHITE : Color.TRANSPARENT);
                view.setLayerType(View.LAYER_TYPE_SOFTWARE, null);
                view.setWebViewClient(new WebViewClient() {
                    @Override public boolean shouldOverrideUrlLoading(WebView source, WebResourceRequest request) {
                        return PicoWebUrlPolicy.navigation(request.getUrl().toString()) == null;
                    }
                    @Override public boolean shouldOverrideUrlLoading(WebView source, String target) {
                        return PicoWebUrlPolicy.navigation(target) == null;
                    }
                    @Override public WebResourceResponse shouldInterceptRequest(WebView source, WebResourceRequest request) {
                        return PicoWebUrlPolicy.resource(request.getUrl().toString()) ? null
                            : new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden",
                                java.util.Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
                    }
                    @Override public void onReceivedSslError(WebView source, SslErrorHandler handler, SslError error) {
                        handler.cancel();
                    }
                    @Override public boolean onRenderProcessGone(WebView source, RenderProcessGoneDetail detail) {
                        Instance current = INSTANCES.get(nativeHandle);
                        if (current != null && current.view == source) {
                            destroyOnMain(nativeHandle);
                            nativeCreationFinished(nativeHandle, false);
                        }
                        return true;
                    }
                    @Override public void onPageStarted(WebView source, String target, Bitmap icon) {
                        Instance current = INSTANCES.get(nativeHandle);
                        if (current == null || !current.active || current.view != source) return;
                        // Navigation retires editor/frame callbacks from the previous document.
                        releaseTextFocus(current);
                        current.stopRendering();
                        current.updateRendering();
                    }
                    @Override public void onPageFinished(WebView finishedView, String finishedUrl) {
                        Instance current = INSTANCES.get(nativeHandle);
                        if (current == null || !current.active || current.view != finishedView) return;
                        if (!current.rendering) current.pauseMedia();
                        finishedView.scrollTo(0, 0);
                        RedactingDiagnostics.i(Event.REDACTED);
                    }
                });
                view.setWebChromeClient(new WebChromeClient() {
                    @Override public void onPermissionRequest(PermissionRequest request) {
                        request.deny();
                    }
                    @Override public void onGeolocationPermissionsShowPrompt(
                            String origin, GeolocationPermissions.Callback callback) {
                        callback.invoke(origin, false, false);
                    }
                });
                WebSettings settings = view.getSettings();
                settings.setJavaScriptEnabled(true);
                settings.setDomStorageEnabled(true);
                settings.setUseWideViewPort(true);
                settings.setAllowFileAccess(false);
                settings.setAllowContentAccess(false);
                settings.setAllowFileAccessFromFileURLs(false);
                settings.setAllowUniversalAccessFromFileURLs(false);
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
                settings.setJavaScriptCanOpenWindowsAutomatically(false);
                settings.setSupportMultipleWindows(false);
                settings.setGeolocationEnabled(false);
                settings.setMediaPlaybackRequiresUserGesture(true);
                settings.setSafeBrowsingEnabled(true);
                CookieManager.getInstance().setAcceptThirdPartyCookies(view, false);
                if (userAgent != null && !userAgent.isEmpty()) {
                    settings.setUserAgentString(userAgent);
                }
                float displayDensity = activity.getResources().getDisplayMetrics().density;
                Instance instance = new Instance(nativeHandle, view, displayDensity);
                if (!instance.resize(width, height)) {
                    view.destroy();
                    RedactingDiagnostics.e(Event.REDACTED);
                    nativeCreationFinished(nativeHandle, false);
                    return;
                }
                INSTANCES.put(nativeHandle, instance);
                // Creation starts dormant. Qt confirms effective surface
                // visibility after the creation handshake; hidden pages do not
                // run an initial document/media/frame before that confirmation.
                instance.pendingUrl = safeUrl;
                view.onPause();
                nativeLifecycle(nativeHandle, instance.epoch, false);
                RedactingDiagnostics.i(Event.REDACTED);
                nativeCreationFinished(nativeHandle, true);
            } catch (RuntimeException | OutOfMemoryError exception) {
                RedactingDiagnostics.e(Event.REDACTED);
                try {
                    if (INSTANCES.containsKey(nativeHandle)) {
                        destroyOnMain(nativeHandle);
                    } else if (view != null) {
                        view.destroy();
                    }
                } catch (RuntimeException | OutOfMemoryError cleanupException) {
                    RedactingDiagnostics.e(Event.REDACTED);
                }
                nativeCreationFinished(nativeHandle, false);
            }
        });
        if (!posted) {
            RedactingDiagnostics.e(Event.REDACTED);
            nativeCreationFinished(nativeHandle, false);
        }
    }

    public static void destroy(long nativeHandle) {
        MAIN.post(() -> destroyOnMain(nativeHandle));
    }

    public static void destroyAll() {
        Runnable destroy = () -> {
            for (long nativeHandle : new ArrayList<>(INSTANCES.keySet())) {
                destroyOnMain(nativeHandle);
            }
        };
        if (Looper.myLooper() == Looper.getMainLooper()) {
            destroy.run();
        } else {
            MAIN.post(destroy);
        }
    }

    /** Android window focus loss must release DOM gestures even without Qt mouse-ungrab. */
    public static void cancelAllInput() {
        Runnable cancel = () -> {
            for (Instance instance : new ArrayList<>(INSTANCES.values())) {
                runCleanupStep("cancel unfocused input", instance::cancelActiveTouch);
                runCleanupStep("release editor focus", () -> releaseTextFocus(instance));
                instance.pendingScroll = 0.0f;
                runCleanupStep("clear view focus", instance.view::clearFocus);
            }
        };
        if (Looper.myLooper() == Looper.getMainLooper()) cancel.run();
        else MAIN.post(cancel);
    }

    private static void destroyOnMain(long nativeHandle) {
        Instance old = INSTANCES.remove(nativeHandle);
        if (old != null) {
            old.active = false;
            runCleanupStep("suspend view", old::suspend);
            runCleanupStep("release editor focus", () -> releaseTextFocus(old));
            runCleanupStep("remove frame callback", old::stopRendering);
            runCleanupStep("cancel touch", old::cancelActiveTouch);
            runCleanupStep("dispose frame buffer", old::disposeGraphics);
            runCleanupStep("stop loading", old.view::stopLoading);
            runCleanupStep("clear page", () -> old.view.loadUrl("about:blank"));
            runCleanupStep("destroy view", old.view::destroy);
            RedactingDiagnostics.i(Event.REDACTED);
        }
    }

    private static void runCleanupStep(String step, Runnable cleanup) {
        try {
            cleanup.run();
        } catch (RuntimeException | OutOfMemoryError exception) {
            RedactingDiagnostics.w(Event.REDACTED);
        }
    }

    public static void load(long nativeHandle, String url) {
        final String safeUrl = PicoWebUrlPolicy.navigation(url);
        postCommand(nativeHandle, "navigation", instance -> {
            releaseTextFocus(instance);
            instance.stopRendering();
            instance.cancelActiveTouch();
            instance.pendingScroll = 0.0f;
            // Invalid replacement content must not leave the previous page interactive.
            instance.pendingUrl = safeUrl == null ? "about:blank" : safeUrl;
            instance.updateRendering();
        });
    }

    public static void setUseBackground(long nativeHandle, boolean useBackground) {
        postCommand(nativeHandle, "background update", instance -> {
            instance.view.setBackgroundColor(
                useBackground ? Color.WHITE : Color.TRANSPARENT);
            instance.view.invalidate();
        });
    }

    public static void setUserAgent(long nativeHandle, String userAgent) {
        postCommand(nativeHandle, "User-Agent update", instance -> {
            instance.view.getSettings().setUserAgentString(
                userAgent == null || userAgent.isEmpty() ? null : userAgent);
        });
    }

    public static void resize(long nativeHandle, int width, int height) {
        postCommand(nativeHandle, "resize", instance -> {
            if (!instance.resize(width, height)) {
                RedactingDiagnostics.e(Event.REDACTED);
            }
        });
    }

    public static void pointer(long nativeHandle, int action, float x, float y) {
        postInputCommand(nativeHandle, "pointer dispatch", instance -> {
            // A click after asynchronous creation/navigation can retain Qt
            // focus without another focusIn event. Reacquire only this admitted
            // native editor owner before delivering the real pointer event.
            if (action == MotionEvent.ACTION_DOWN) requestTextFocus(instance);
            instance.dispatchPointer(action, x, y);
            instance.publishEditorState();
        });
    }

    private static void releaseTextFocus(Instance instance) {
        if (textFocus != instance) return;
        textFocus = null;
        instance.clearEditorState();
        InputConnection input = instance.view.onCreateInputConnection(new EditorInfo());
        if (input != null) {
            input.finishComposingText();
        }
        instance.view.clearFocus();
    }

    private static void requestTextFocus(Instance instance) {
        if (textFocus == instance && instance.view.hasFocus()) return;
        if (textFocus != null) releaseTextFocus(textFocus);
        PicoInterfaceActivity owner = PicoInterfaceActivity.getInstance();
        PicoWebInputGate.Ticket ticket = INPUT_GATE.capture();
        if (ticket == null || !instance.mayRender() || instance.view.getContext() != owner) return;
        if (instance.view.requestFocus() && INPUT_GATE.permits(ticket, owner) && instance.mayRender()) textFocus = instance;
    }

    public static void focus(long nativeHandle, boolean focused) {
        postInputCommand(nativeHandle, "editor focus", instance -> {
            if (!focused) { releaseTextFocus(instance); return; }
            requestTextFocus(instance);
            instance.publishEditorState();
        });
    }

    private static InputConnection focusedEditor(Instance instance) {
        PicoInterfaceActivity activity = PicoInterfaceActivity.getInstance();
        if (textFocus != instance || !instance.active || !instance.view.hasFocus()
                || activity == null || !activity.hasWindowFocus()) return null;
        return instance.view.onCreateInputConnection(new EditorInfo());
    }

    public static void editText(long nativeHandle, String text, boolean composing) {
        if (!PicoTextInput.valid(text)) return;
        postInputCommand(nativeHandle, "editor text", instance -> {
            if (!PicoTextInput.text(focusedEditor(instance), text, composing)) {
                RedactingDiagnostics.w(Event.CALLBACK_DISCARDED);
            }
        });
    }

    public static void editKey(long nativeHandle, int key) {
        postInputCommand(nativeHandle, "editor key", instance -> {
            if (!PicoTextInput.key(focusedEditor(instance), key)) {
                RedactingDiagnostics.w(Event.CALLBACK_DISCARDED);
            }
        });
    }

    public static void scroll(long nativeHandle, float x, float y, float delta) {
        postInputCommand(nativeHandle, "scroll dispatch", instance -> {
            // Pico's analogue thumbstick supplies small wheel fractions every input
            // frame. Android WebView ignores those fractions individually, while
            // forwarding a full wheel unit every frame scrolls far too quickly.
            instance.pendingScroll += delta;
            if (Math.abs(instance.pendingScroll) < 1.0f) {
                return;
            }
            float wheelStep = Math.signum(instance.pendingScroll);
            instance.pendingScroll -= wheelStep;
            // Programmatic DOM scrolling preserves CSS clipping and fixed elements
            // when this unattached WebView is rendered into a software Canvas.
            // Native WebView.scrollBy() moves the entire offscreen layer, does not
            // clamp it, and exposes blank background at either end.
            String script = String.format(Locale.US,
                "(function(x,y,d){var e=document.elementFromPoint(x,y),s;"
                + "while(e&&e!==document.body&&e!==document.documentElement){"
                + "s=getComputedStyle(e);if(e.scrollHeight>e.clientHeight&&"
                + "(s.overflowY==='auto'||s.overflowY==='scroll')){"
                + "e.scrollTop+=d;return;}e=e.parentElement;}"
                + "e=document.scrollingElement||document.documentElement;"
                + "e.scrollTop+=d;"
                + "})(%.3f,%.3f,%.3f)",
                x, y, -wheelStep * 120.0f);
            final long surfaceEpoch = instance.epoch;
            final long visibilityRevision = instance.visibilityRevision;
            instance.view.evaluateJavascript(script, result -> {
                // An unattached software WebView does not receive ViewRootImpl's
                // normal invalidation/layout pass after compositor scrolling.
                // Force that pass so draw(Canvas) cannot reuse stale page layers.
                // The callback can arrive after destroy or after a replacement
                // WebView has reused the same native handle.
                if (instance.active && instance.epoch == surfaceEpoch
                        && instance.visibilityRevision == visibilityRevision && instance.mayRender()
                        && INSTANCES.get(nativeHandle) == instance) {
                    try {
                        instance.refreshLayout();
                    } catch (RuntimeException | OutOfMemoryError exception) {
                        failCurrentInstance(
                            nativeHandle, instance, "scroll layout", exception);
                    }
                }
            });
        });
    }

    private static final class Instance {
        final long nativeHandle;
        final WebView view;
        final float displayDensity;
        volatile boolean active = true;
        volatile boolean visible;
        volatile boolean rendering;
        volatile long epoch = frameEpoch();
        volatile long visibilityRevision = frameEpoch();
        String pendingUrl;
        Runnable pendingFrame;
        Bitmap bitmap;
        Canvas canvas;
        ByteBuffer pixels;
        boolean reportedFirstFrame;
        float pendingScroll;
        final PicoTouchState touchState = new PicoTouchState();
        PicoWebEditorState editorState = PicoWebEditorState.INACTIVE;

        void publishEditorState() {
            PicoInterfaceActivity owner = PicoInterfaceActivity.getInstance();
            PicoWebInputGate.Ticket ticket = INPUT_GATE.capture();
            final long observedEpoch = epoch, observedVisibility = visibilityRevision;
            boolean admitted = mayRender() && textFocus == this && ticket != null
                && owner != null && owner.hasWindowFocus() && INPUT_GATE.permits(ticket, owner);
            PicoWebEditorState next = PicoWebEditorState.inspect(view, admitted);
            // Native APIs can synchronously dispatch callbacks; recheck the same lease.
            if (!mayRender() || epoch != observedEpoch || visibilityRevision != observedVisibility
                    || ticket == null || !INPUT_GATE.permits(ticket, owner)) next = PicoWebEditorState.INACTIVE;
            if (editorState.same(next)) return;
            sendEditorState(next);
        }

        void clearEditorState() { sendEditorState(PicoWebEditorState.INACTIVE); }

        void sendEditorState(PicoWebEditorState next) {
            editorState = next;
            long revision = frameEpoch();
            if (revision == 0) {
                editorState = PicoWebEditorState.INACTIVE;
                epoch = 0; rendering = false;
                Runnable callback = pendingFrame; pendingFrame = null;
                if (callback != null) MAIN.removeCallbacks(callback);
                nativeLifecycle(nativeHandle, Long.MAX_VALUE, false);
                return;
            }
            nativeEditorState(nativeHandle, epoch, revision, next.focused, next.numeric, next.password);
        }

        final Runnable renderFrame = new Runnable() {
            @Override public void run() {
                if (!mayRender() || bitmap == null) {
                    return;
                }
                final long renderedEpoch = epoch;
                final long renderedVisibility = visibilityRevision;
                final PicoWebInputGate.Ticket ticket = FRAME_GATE.capture();
                if (ticket == null) return;
                try {
                    bitmap.eraseColor(0x00000000);
                    int saveCount = canvas.save();
                    try {
                        canvas.translate(-view.getScrollX(), -view.getScrollY());
                        view.draw(canvas);
                    } finally {
                        canvas.restoreToCount(saveCount);
                    }
                    pixels.rewind();
                    bitmap.copyPixelsToBuffer(pixels);
                    pixels.rewind();
                    // Recheck admission after rasterization: an Activity pause
                    // can invalidate its epoch from another thread meanwhile.
                    if (!mayRender() || renderedEpoch != epoch || renderedVisibility != visibilityRevision
                            || !FRAME_GATE.permits(ticket, PicoInterfaceActivity.getInstance())) return;
                    publishEditorState();
                    if (!mayRender() || epoch != renderedEpoch || visibilityRevision != renderedVisibility
                            || !FRAME_GATE.permits(ticket, PicoInterfaceActivity.getInstance())) return;
                    nativeFrame(nativeHandle, renderedEpoch, pixels, bitmap.getWidth(), bitmap.getHeight());
                    if (!reportedFirstFrame) {
                        reportedFirstFrame = true;
                        RedactingDiagnostics.i(Event.REDACTED);
                    }
                } catch (RuntimeException | OutOfMemoryError exception) {
                    RedactingDiagnostics.e(Event.REDACTED);
                    try {
                        destroyOnMain(nativeHandle);
                    } catch (RuntimeException | OutOfMemoryError cleanupException) {
                        RedactingDiagnostics.e(Event.REDACTED);
                    }
                    nativeCreationFinished(nativeHandle, false);
                    return;
                }
                if (mayRender() && !scheduleFrame(FRAME_INTERVAL_MS)) {
                    RedactingDiagnostics.e(Event.REDACTED);
                    destroyOnMain(nativeHandle);
                    nativeCreationFinished(nativeHandle, false);
                }
            }
        };

        Instance(long nativeHandle, WebView view, float displayDensity) {
            this.nativeHandle = nativeHandle;
            this.view = view;
            this.displayDensity = Math.max(1.0f, displayDensity);
        }

        boolean mayRender() {
            PicoInterfaceActivity owner = PicoInterfaceActivity.getInstance();
            return epoch > 0 && visibilityRevision > 0 && active && visible && rendering && INSTANCES.get(nativeHandle) == this
                && view.getContext() == owner && FRAME_GATE.capture() != null;
        }

        boolean scheduleFrame(long delay) {
            final PicoWebInputGate.Ticket ticket = FRAME_GATE.capture();
            if (ticket == null || !mayRender()) return true;
            final long scheduledEpoch = epoch;
            final long scheduledVisibility = visibilityRevision;
            final Runnable callback = () -> {
                if (scheduledEpoch != epoch || scheduledVisibility != visibilityRevision || !mayRender()
                        || !FRAME_GATE.permits(ticket, PicoInterfaceActivity.getInstance())) return;
                pendingFrame = null;
                renderFrame.run();
            };
            pendingFrame = callback;
            return MAIN.postDelayed(callback, delay);
        }

        void stopRendering() {
            clearEditorState();
            epoch = frameEpoch();
            rendering = false;
            Runnable callback = pendingFrame;
            pendingFrame = null;
            if (callback != null) MAIN.removeCallbacks(callback);
            nativeLifecycle(nativeHandle, epoch == 0 ? Long.MAX_VALUE : epoch, false);
        }

        void pauseMedia() {
            // Per-view media only. WebView.pauseTimers() would also suspend
            // unrelated active world/tablet pages in the same process.
            view.evaluateJavascript("document.querySelectorAll('video,audio').forEach(function(m){m.pause();});", null);
        }

        void suspend() {
            runCleanupStep("remove frame callback", this::stopRendering);
            runCleanupStep("pause page media", this::pauseMedia);
            runCleanupStep("pause view", view::onPause);
            runCleanupStep("release editor focus", () -> releaseTextFocus(this));
            runCleanupStep("cancel touch", this::cancelActiveTouch);
            pendingScroll = 0;
        }

        void updateRendering() {
            PicoInterfaceActivity owner = PicoInterfaceActivity.getInstance();
            boolean allowed = active && visible && view.getContext() == owner
                && FRAME_GATE.capture() != null && epoch > 0;
            if (!allowed) { suspend(); return; }
            if (rendering) return;
            epoch = frameEpoch();
            if (epoch == 0) { suspend(); return; }
            rendering = true;
            view.onResume();
            nativeLifecycle(nativeHandle, epoch, true);
            if (pendingUrl != null) {
                String pending = pendingUrl;
                pendingUrl = null;
                view.loadUrl(pending);
            }
            if (!scheduleFrame(0)) {
                failCurrentInstance(nativeHandle, this, "frame scheduling", new IllegalStateException());
            }
        }

        void dispatchPointer(int action, float x, float y) {
            long now = android.os.SystemClock.uptimeMillis();
            boolean hover = action == MotionEvent.ACTION_HOVER_ENTER
                || action == MotionEvent.ACTION_HOVER_MOVE
                || action == MotionEvent.ACTION_HOVER_EXIT;
            if (!hover && action == MotionEvent.ACTION_DOWN && touchState.isActive()) {
                dispatchPointer(MotionEvent.ACTION_CANCEL, x, y);
            } else if (!hover && action != MotionEvent.ACTION_DOWN && !touchState.isActive()) {
                return;
            }
            long downTime = hover ? now : touchState.downTimeFor(action, now);
            MotionEvent event = MotionEvent.obtain(downTime, now, action,
                x * displayDensity, y * displayDensity, 0);
            event.setSource(hover
                ? InputDevice.SOURCE_MOUSE : InputDevice.SOURCE_TOUCHSCREEN);
            if (hover) {
                view.dispatchGenericMotionEvent(event);
            } else {
                view.dispatchTouchEvent(event);
            }
            event.recycle();
        }

        void cancelActiveTouch() {
            if (touchState.isActive()) {
                dispatchPointer(MotionEvent.ACTION_CANCEL, 0.0f, 0.0f);
            }
        }

        void refreshLayout() {
            int width = Math.max(1, view.getWidth());
            int height = Math.max(1, view.getHeight());
            view.forceLayout();
            view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
            view.layout(0, 0, width, height);
            view.invalidate();
        }

        boolean resize(int requestedWidth, int requestedHeight) {
            int width = Math.max(1, requestedWidth);
            int height = Math.max(1, requestedHeight);
            int longestEdge = Math.max(width, height);
            if (longestEdge > MAX_TEXTURE_EDGE) {
                float scale = (float) MAX_TEXTURE_EDGE / longestEdge;
                width = Math.max(1, Math.round(width * scale));
                height = Math.max(1, Math.round(height * scale));
            }
            if (bitmap != null && bitmap.getWidth() == width && bitmap.getHeight() == height) {
                return true;
            }
            Bitmap newBitmap = null;
            Canvas newCanvas;
            ByteBuffer newPixels;
            try {
                newBitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
                newCanvas = new Canvas(newBitmap);
                newCanvas.scale(1.0f / displayDensity, 1.0f / displayDensity);
                newPixels = ByteBuffer.allocateDirect(width * height * 4);
                int layoutWidth = Math.max(1, Math.round(width * displayDensity));
                int layoutHeight = Math.max(1, Math.round(height * displayDensity));
                int widthSpec = View.MeasureSpec.makeMeasureSpec(
                    layoutWidth, View.MeasureSpec.EXACTLY);
                int heightSpec = View.MeasureSpec.makeMeasureSpec(
                    layoutHeight, View.MeasureSpec.EXACTLY);
                view.measure(widthSpec, heightSpec);
                view.layout(0, 0, layoutWidth, layoutHeight);
            } catch (RuntimeException | OutOfMemoryError exception) {
                if (newBitmap != null && !newBitmap.isRecycled()) {
                    newBitmap.recycle();
                }
                RedactingDiagnostics.e(Event.REDACTED);
                return false;
            }
            Bitmap oldBitmap = bitmap;
            bitmap = newBitmap;
            canvas = newCanvas;
            pixels = newPixels;
            if (oldBitmap != null && !oldBitmap.isRecycled()) {
                oldBitmap.recycle();
            }
            return true;
        }

        void disposeGraphics() {
            Bitmap oldBitmap = bitmap;
            bitmap = null;
            canvas = null;
            pixels = null;
            if (oldBitmap != null && !oldBitmap.isRecycled()) {
                oldBitmap.recycle();
            }
        }
    }
}
