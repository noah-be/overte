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
    private static final int FRAME_INTERVAL_MS = 100;
    private static final int MAX_TEXTURE_EDGE = 2048;
    private static boolean wholeDocumentDrawEnabled;
    private static Instance textFocus;

    private OffscreenWebView() { }

    public static void initializeNativeBridge() {
        nativeInitialize();
    }

    private static native void nativeInitialize();
    private static native void nativeCreationFinished(long nativeHandle, boolean created);
    private static native void nativeFrame(
        long nativeHandle, ByteBuffer pixels, int width, int height);

    private interface InstanceCommand {
        void run(Instance instance);
    }

    private static void postCommand(long nativeHandle, String name, InstanceCommand command) {
        boolean posted = MAIN.post(() -> {
            Instance instance = INSTANCES.get(nativeHandle);
            if (instance == null) {
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
        postCommand(handle, name, instance -> {
            if (instance != target.get()) return;
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
        boolean posted = MAIN.post(() -> {
            WebView view = null;
            try {
                destroyOnMain(nativeHandle);
                PicoInterfaceActivity activity = PicoInterfaceActivity.getInstance();
                if (activity == null) {
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
                    @Override public void onPageFinished(WebView finishedView, String finishedUrl) {
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
                view.loadUrl(safeUrl);
                RedactingDiagnostics.i(Event.REDACTED);
                if (!MAIN.post(instance.renderFrame)) {
                    RedactingDiagnostics.e(Event.REDACTED);
                    destroyOnMain(nativeHandle);
                    nativeCreationFinished(nativeHandle, false);
                    return;
                }
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
            runCleanupStep("release editor focus", () -> releaseTextFocus(old));
            runCleanupStep("remove frame callback", () -> MAIN.removeCallbacks(old.renderFrame));
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
            instance.cancelActiveTouch();
            instance.pendingScroll = 0.0f;
            // Invalid replacement content must not leave the previous page interactive.
            instance.view.loadUrl(safeUrl == null ? "about:blank" : safeUrl);
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
            instance.dispatchPointer(action, x, y);
        });
    }

    private static void releaseTextFocus(Instance instance) {
        if (textFocus != instance) return;
        textFocus = null;
        InputConnection input = instance.view.onCreateInputConnection(new EditorInfo());
        if (input != null) {
            input.finishComposingText();
        }
        instance.view.clearFocus();
    }

    public static void focus(long nativeHandle, boolean focused) {
        postInputCommand(nativeHandle, "editor focus", instance -> {
            if (!focused) { releaseTextFocus(instance); return; }
            if (textFocus != null && textFocus != instance) releaseTextFocus(textFocus);
            if (instance.view.requestFocus()) textFocus = instance;
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
            instance.view.evaluateJavascript(script, result -> {
                // An unattached software WebView does not receive ViewRootImpl's
                // normal invalidation/layout pass after compositor scrolling.
                // Force that pass so draw(Canvas) cannot reuse stale page layers.
                // The callback can arrive after destroy or after a replacement
                // WebView has reused the same native handle.
                if (instance.active && INSTANCES.get(nativeHandle) == instance) {
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
        boolean active = true;
        Bitmap bitmap;
        Canvas canvas;
        ByteBuffer pixels;
        boolean reportedFirstFrame;
        float pendingScroll;
        final PicoTouchState touchState = new PicoTouchState();

        final Runnable renderFrame = new Runnable() {
            @Override public void run() {
                if (!active || bitmap == null) {
                    return;
                }
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
                    nativeFrame(nativeHandle, pixels, bitmap.getWidth(), bitmap.getHeight());
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
                if (active && INSTANCES.get(nativeHandle) == Instance.this) {
                    if (!MAIN.postDelayed(this, FRAME_INTERVAL_MS)) {
                        RedactingDiagnostics.e(Event.REDACTED);
                        destroyOnMain(nativeHandle);
                        nativeCreationFinished(nativeHandle, false);
                    }
                }
            }
        };

        Instance(long nativeHandle, WebView view, float displayDensity) {
            this.nativeHandle = nativeHandle;
            this.view = view;
            this.displayDensity = Math.max(1.0f, displayDensity);
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
