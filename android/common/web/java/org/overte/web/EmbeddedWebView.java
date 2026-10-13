// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

import android.annotation.SuppressLint;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Rect;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.InputDevice;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.webkit.ScriptHandler;
import androidx.webkit.WebMessageCompat;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.lang.ref.WeakReference;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.concurrent.ConcurrentHashMap;

/** Shared native HTML runtime; product hosts own presentation and OS prompts. */
public final class EmbeddedWebView {
    public static final int READY = 0, BRIDGE_UNAVAILABLE = 1, LOAD_FAILED = 2,
        RUNTIME_FAILED = 3, OVERLAY_UNAVAILABLE = 4, FILE_CHOOSER_UNAVAILABLE = 5, EXTERNAL_UNAVAILABLE = 8;
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final ConcurrentHashMap<Long, Instance> VIEWS = new ConcurrentHashMap<>();
    private static final WebInputGate INPUT = new WebInputGate();
    private static WeakReference<EmbeddedWebHost> host = new WeakReference<>(null);
    private static boolean wholeDocumentDraw;
    private EmbeddedWebView() { }

    /** Call on the Android UI thread after the product native library is loaded. */
    public static void initialize(EmbeddedWebHost next) {
        requireMain();
        if (host.get() != next) { destroyAll(); }
        host = new WeakReference<>(next);
        nativeInitialize();
        setForeground(next, next != null && next.isForeground());
    }
    public static void setForeground(EmbeddedWebHost owner, boolean foreground) {
        requireMain();
        if (host.get() != owner) return;
        INPUT.update(owner, foreground);
        nativeForeground(foreground);
        for (Instance instance : new ArrayList<>(VIEWS.values())) {
            instance.document.grant(nativeGeneration(instance.handle));
            if (!foreground) { instance.suspend(); }
            else if (instance.visible) { instance.view.onResume(); instance.authorize(); instance.publish(); }
        }
    }
    public static void detach(EmbeddedWebHost owner) {
        requireMain();
        if (host.get() != owner) return;
        setForeground(owner, false); destroyAll(); host.clear();
    }
    private static void requireMain() {
        if (Looper.myLooper() != Looper.getMainLooper()) throw new IllegalStateException("UI thread required");
    }
    private static native void nativeInitialize();
    private static native void nativeForeground(boolean active);
    private static native long nativeGeneration(long handle);
    private static native boolean nativeBridgeAllowed(long handle, long grant, long page, String document);
    private static native boolean nativeFileChooserAllowed(long handle, long grant, long page, String document);
    private static native boolean nativeNavigation(long handle, long grant, String url, boolean mainFrame, String method);
    private static native boolean nativeMessage(long handle, long grant, long page, String document,
                                               String origin, boolean mainFrame, String type, String payload);
    private static native void nativePage(long handle, long grant, long page, String url);
    private static native void nativeState(long handle, long grant, long page, String url,
                                           boolean loading, boolean canGoBack, boolean canGoForward, boolean bridge, int status);
    private static native void nativeResult(long handle, long grant, long page, long request, String json);
    private static native void nativeCreated(long handle, boolean created);
    private static native void nativeFrame(long handle, long grant, long page, ByteBuffer pixels, int width, int height);
    private static native byte[] nativeResource(long handle, long grant, String url);
    private static native String nativeResourceMime(long handle, long grant, String url);

    private interface Command { void run(Instance instance); }
    private static void post(long handle, Command command) {
        if (!MAIN.post(() -> {
            Instance instance = VIEWS.get(handle);
            if (instance == null || !instance.active) return;
            try { command.run(instance); }
            catch (RuntimeException | OutOfMemoryError failure) { instance.fail(RUNTIME_FAILED); }
        })) { nativeCreated(handle, false); }
    }
    private static void input(long handle, Command command) {
        WebInputGate.Ticket ticket = INPUT.capture();
        Instance expected = VIEWS.get(handle);
        if (ticket == null || expected == null) return;
        WeakReference<Instance> target = new WeakReference<>(expected);
        post(handle, instance -> {
            EmbeddedWebHost owner = host.get();
            if (instance != target.get() || !INPUT.permits(ticket, owner) || !instance.visible
                    || !owner.isForeground() || owner.activity() != instance.view.getContext()
                    || !owner.activity().hasWindowFocus()) return;
            command.run(instance);
        });
    }
    @SuppressLint("SetJavaScriptEnabled")
    public static void create(long handle, long grant, String url, String userAgent,
            boolean background, boolean overlay, int x, int y, int width, int height,
            int clipX, int clipY, int clipWidth, int clipHeight, String bootstrap) {
        MAIN.post(() -> {
            EmbeddedWebHost owner = host.get();
            if (nativeGeneration(handle) != grant || owner == null || owner.activity() == null || width <= 1 || height <= 1) {
                nativeCreated(handle, false); return;
            }
            destroyOnMain(handle);
            WebView view = null;
            try {
                if (!wholeDocumentDraw) { WebView.enableSlowWholeDocumentDraw(); wholeDocumentDraw = true; }
                view = new WebView(owner.activity());
                WebSettings settings = view.getSettings();
                settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true);
                settings.setAllowFileAccess(false); settings.setAllowContentAccess(false);
                settings.setAllowFileAccessFromFileURLs(false); settings.setAllowUniversalAccessFromFileURLs(false);
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
                settings.setJavaScriptCanOpenWindowsAutomatically(false); settings.setSupportMultipleWindows(false);
                settings.setGeolocationEnabled(false); settings.setMediaPlaybackRequiresUserGesture(true);
                if (android.os.Build.VERSION.SDK_INT >= 26) settings.setSafeBrowsingEnabled(true);
                settings.setUseWideViewPort(true);
                if (userAgent != null && !userAgent.isEmpty()) settings.setUserAgentString(userAgent);
                CookieManager.getInstance().setAcceptThirdPartyCookies(view, false);
                view.setBackgroundColor(background ? Color.WHITE : Color.TRANSPARENT);
                Instance instance = new Instance(handle, view, overlay, bootstrap);
                instance.document.begin(grant);
                instance.bounds = new Rect(x, y, x + width, y + height);
                instance.clip = new Rect(clipX, clipY, clipX + clipWidth, clipY + clipHeight);
                instance.resize(width, height);
                VIEWS.put(handle, instance);
                instance.configureBridge(url);
                view.setWebViewClient(instance.client);
                view.setWebChromeClient(instance.chrome);
                if (overlay) {
                    if (!owner.placeTabletView(view, instance.bounds, instance.clip)) instance.status = OVERLAY_UNAVAILABLE;
                } else { view.setLayerType(View.LAYER_TYPE_SOFTWARE, null); }
                view.loadUrl(url);
                if (!overlay) MAIN.post(instance.frame);
                nativeCreated(handle, true);
                instance.publish();
            } catch (RuntimeException | OutOfMemoryError failure) {
                if (VIEWS.containsKey(handle)) destroyOnMain(handle);
                else if (view != null) view.destroy();
                owner.diagnostic(RUNTIME_FAILED); nativeCreated(handle, false);
            }
        });
    }
    public static void destroy(long handle) { MAIN.post(() -> destroyOnMain(handle)); }
    private static void destroyAll() {
        requireMain(); for (long handle : new ArrayList<>(VIEWS.keySet())) destroyOnMain(handle);
    }
    private static void destroyOnMain(long handle) {
        Instance instance = VIEWS.remove(handle);
        if (instance == null) return;
        instance.active = false; instance.document.close();
        instance.cancelInput(); MAIN.removeCallbacks(instance.frame);
        EmbeddedWebHost owner = host.get();
        if (owner != null && instance.overlay) owner.removeTabletView(instance.view);
        if (instance.script != null) instance.script.remove();
        instance.view.stopLoading(); instance.view.loadUrl("about:blank"); instance.view.destroy();
        if (instance.bitmap != null) instance.bitmap.recycle();
        nativeCreated(handle, false);
    }
    public static void load(long handle, long grant, String url) {
        post(handle, instance -> {
            if (nativeGeneration(handle) != grant) return;
            instance.document.begin(grant); instance.cancelInput(); instance.configureBridge(url);
            instance.view.loadUrl(url);
        });
    }
    public static void visibility(long handle, long grant, boolean visible) {
        post(handle, instance -> {
            if (nativeGeneration(handle) != grant) return;
            instance.document.grant(grant); instance.document.visible(visible); instance.visible = visible;
            instance.view.setVisibility(visible ? View.VISIBLE : View.GONE);
            if (!visible) { instance.suspend(); instance.publish(); }
            else { instance.view.onResume(); instance.authorize(); instance.publish(); }
        });
    }
    public static void resize(long handle, int x, int y, int width, int height, int clipX, int clipY, int clipWidth, int clipHeight) {
        post(handle, instance -> {
            instance.bounds = new Rect(x, y, x + width, y + height);
            instance.clip = new Rect(clipX, clipY, clipX + clipWidth, clipY + clipHeight);
            instance.resize(width, height);
            EmbeddedWebHost owner = host.get();
            if (instance.overlay && owner != null && !owner.placeTabletView(instance.view, instance.bounds, instance.clip)) {
                instance.status = OVERLAY_UNAVAILABLE; instance.publish();
            }
        });
    }
    public static void relayout(EmbeddedWebHost expected) {
        MAIN.post(() -> {
            if (host.get() != expected) return;
            for (Instance instance : VIEWS.values()) {
                if (!instance.active || !instance.overlay || instance.view.getContext() != expected.activity()) continue;
                boolean placed = expected.placeTabletView(instance.view, instance.bounds, instance.clip);
                if (placed && instance.status == OVERLAY_UNAVAILABLE) {
                    instance.status = instance.bridge ? READY : BRIDGE_UNAVAILABLE;
                    instance.publish();
                }
            }
        });
    }
    public static void background(long handle, boolean value) {
        post(handle, instance -> instance.view.setBackgroundColor(value ? Color.WHITE : Color.TRANSPARENT));
    }
    public static void userAgent(long handle, String value) {
        post(handle, instance -> instance.view.getSettings().setUserAgentString(value.isEmpty() ? null : value));
    }
    public static void stop(long handle) { post(handle, instance -> { instance.view.stopLoading(); instance.loading = false; instance.publish(); }); }
    public static void reload(long handle) { input(handle, instance -> { instance.document.begin(instance.document.grant()); instance.view.reload(); }); }
    public static void goForward(long handle) { input(handle, instance -> { if (instance.view.canGoForward()) { instance.document.begin(instance.document.grant()); instance.view.goForward(); } }); }
    public static void reloadAndBypassCache(long handle) { input(handle, instance -> { instance.view.clearCache(false); instance.document.begin(instance.document.grant()); instance.view.reload(); }); }
    public static void openNative(long handle) { input(handle, instance -> {
        String url = instance.view.getUrl();
        if (url != null && nativeNavigation(handle, instance.document.grant(), url, true, "GET")
                && !"overte-embedded.invalid".equals(Uri.parse(url).getHost())) {
            EmbeddedWebHost owner = host.get();
            if (owner != null && !owner.openExternal(Uri.parse(url))) { instance.status = EXTERNAL_UNAVAILABLE; instance.publish(); }
        }
    }); }
    public static void goBack(long handle) { input(handle, instance -> { if (instance.view.canGoBack()) { instance.document.begin(instance.document.grant()); instance.view.goBack(); } }); }
    public static void evaluate(long handle, long grant, long page, String javascript) {
        post(handle, instance -> {
            if (!instance.document.admits(grant, page, true, 1)) return;
            instance.view.evaluateJavascript(javascript, null);
        });
    }
    public static void evaluateResult(long handle, long grant, long page, long request, String javascript) {
        post(handle, instance -> {
            if (!instance.document.admits(grant, page, true, 1)) return;
            instance.view.evaluateJavascript(javascript, result -> {
                if (result != null && result.length() <= 65536 && instance.document.admits(grant, page, true, result.getBytes(StandardCharsets.UTF_8).length))
                    nativeResult(handle, grant, page, request, result);
            });
        });
    }
    public static void pointer(long handle, int action, float x, float y) {
        input(handle, instance -> instance.dispatchPointer(action, x, y));
    }
    public static void focus(long handle, boolean focused) {
        input(handle, instance -> {
            if (focused) { instance.view.requestFocus(); instance.editorPublish(); }
            else { instance.cancelInput(); }
        });
    }
    private static final class Instance {
        final long handle;
        final WebView view;
        final boolean overlay;
        final String bootstrap;
        final WebDocumentState document = new WebDocumentState();
        Rect bounds, clip;
        WebTextureScale textureScale;
        Bitmap bitmap;
        Canvas canvas;
        ByteBuffer pixels;
        ScriptHandler script;
        boolean active = true, visible = true, loading, bridge;
        final WebPointerState pointerState = new WebPointerState();
        int status;
        long pickerLease;
        String requestedUrl = "about:blank";
        Instance(long handle, WebView view, boolean overlay, String bootstrap) {
            this.handle = handle; this.view = view; this.overlay = overlay; this.bootstrap = bootstrap;
        }
        void configureBridge(String url) {
            requestedUrl = url;
            if (script != null) { script.remove(); script = null; }
            if (bridge) WebViewCompat.removeWebMessageListener(view, "__overteNative");
            bridge = WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)
                && WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT);
            status = bridge ? READY : BRIDGE_UNAVAILABLE;
            if (!bridge) return;
            String origin = origin(url);
            if (origin == null) { bridge = false; status = BRIDGE_UNAVAILABLE; return; }
            WebViewCompat.addWebMessageListener(view, "__overteNative", Collections.singleton(origin),
                (source, message, sourceOrigin, mainFrame, reply) -> {
                    if (source != view || !active || message.getType() != WebMessageCompat.TYPE_STRING) return;
                    String encoded = message.getData();
                    if (encoded == null || encoded.length() > 65536) return;
                    int bytes = encoded.getBytes(StandardCharsets.UTF_8).length;
                    try {
                        JSONObject envelope = new JSONObject(encoded);
                        long grant = Long.parseLong(envelope.getString("grant"));
                        long page = Long.parseLong(envelope.getString("page"));
                        if (!document.admits(grant, page, mainFrame, bytes)) return;
                        String type = envelope.getString("type");
                        String payload = type.equals("channel") ? envelope.getString("payload")
                            : envelope.getJSONObject("payload").toString();
                        nativeMessage(handle, grant, page, view.getUrl(), sourceOrigin.toString(), mainFrame, type, payload);
                    } catch (Exception invalid) { /* No untrusted payload is logged. */ }
                });
            script = WebViewCompat.addDocumentStartJavaScript(view, bootstrap, Collections.singleton(origin));
        }
        void authorize() {
            if (!active || !visible || !bridge || loading) return;
            EmbeddedWebHost owner = host.get();
            if (owner == null || !owner.isForeground()) return;
            String javascript = "window.__overteTransport&&window.__overteTransport.authorize("
                + JSONObject.quote(Long.toString(document.grant())) + ","
                + JSONObject.quote(Long.toString(document.page())) + ");"
                + "window.__overteEditor&&window.__overteEditor.publish();";
            view.evaluateJavascript(javascript, null);
        }
        void editorPublish() { view.evaluateJavascript("window.__overteEditor&&window.__overteEditor.publish();", null); }
        void suspend() {
            cancelInput();
            view.evaluateJavascript("document.querySelectorAll('video,audio').forEach(function(m){m.pause();});", null); view.evaluateJavascript("window.__overteTransport&&window.__overteTransport.suspend();", null);
            view.onPause();
        }
        void dispatchPointer(int action, float x, float y) {
            if (!Float.isFinite(x) || !Float.isFinite(y)) return;
            if (action == MotionEvent.ACTION_DOWN && pointerState.pressed()) dispatchPointer(MotionEvent.ACTION_CANCEL, 0, 0);
            long now = SystemClock.uptimeMillis(), down = pointerState.downTime();
            if (!pointerState.accept(action, now)) return;
            boolean hover = WebPointerState.hover(action);
            if (action == MotionEvent.ACTION_DOWN) down = pointerState.downTime();
            MotionEvent event = MotionEvent.obtain(hover ? now : down, now, action,
                overlay ? x : textureScale.pointer(x), overlay ? y : textureScale.pointer(y), 0);
            event.setSource(hover ? InputDevice.SOURCE_MOUSE : InputDevice.SOURCE_TOUCHSCREEN);
            try { if (hover) view.dispatchGenericMotionEvent(event); else view.dispatchTouchEvent(event); }
            finally { event.recycle(); }
        }
        void cancelInput() {
            if (pointerState.pressed()) dispatchPointer(MotionEvent.ACTION_CANCEL, 0, 0);
            if (pointerState.hovering()) dispatchPointer(MotionEvent.ACTION_HOVER_EXIT, 0, 0);
            view.evaluateJavascript("window.__overteEditor&&window.__overteEditor.blur();", null);
            view.clearFocus();
        }
        void resize(int width, int height) {
            if (width <= 1 || height <= 1) return;
            textureScale = overlay ? null : new WebTextureScale(width, height, view.getResources().getDisplayMetrics().density);
            int w = overlay ? width : textureScale.width, h = overlay ? height : textureScale.height;
            int layoutWidth = overlay ? width : textureScale.layoutWidth, layoutHeight = overlay ? height : textureScale.layoutHeight;
            view.forceLayout();
            view.measure(View.MeasureSpec.makeMeasureSpec(layoutWidth, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(layoutHeight, View.MeasureSpec.EXACTLY));
            view.layout(0, 0, layoutWidth, layoutHeight);
            if (overlay) return;
            if (bitmap != null) bitmap.recycle();
            bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888); canvas = new Canvas(bitmap); canvas.scale(1.0f / textureScale.density, 1.0f / textureScale.density);
            pixels = ByteBuffer.allocateDirect(w * h * 4);
        }
        void publish() {
            int presentationStatus = status;
            if (presentationStatus == READY && bridge && !loading
                    && !nativeBridgeAllowed(handle, document.grant(), document.page(), view.getUrl())) presentationStatus = 9;
            nativeState(handle, document.grant(), document.page(), view.getUrl(), loading, view.canGoBack(), view.canGoForward(), bridge, presentationStatus);
            EmbeddedWebHost owner = host.get(); if (owner != null && active) owner.statusChanged(view, presentationStatus);
        }
        void fail(int failure) {
            status = failure; publish(); EmbeddedWebHost owner = host.get(); if (owner != null) owner.diagnostic(failure);
            destroyOnMain(handle);
        }
        final Runnable frame = new Runnable() { public void run() {
            if (!active) return;
            EmbeddedWebHost owner = host.get();
            if (visible && owner != null && owner.isForeground() && bitmap != null) {
                try {
                    bitmap.eraseColor(Color.TRANSPARENT); view.draw(canvas); pixels.rewind();
                    bitmap.copyPixelsToBuffer(pixels); pixels.rewind();
                    nativeFrame(handle, document.grant(), document.page(), pixels, bitmap.getWidth(), bitmap.getHeight());
                } catch (RuntimeException | OutOfMemoryError failure) { fail(RUNTIME_FAILED); return; }
            }
            MAIN.postDelayed(this, 100);
        }};
        final WebViewClient client = new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView source, WebResourceRequest request) {
                return !nativeNavigation(handle, document.grant(), request.getUrl().toString(), request.isForMainFrame(), request.getMethod());
            }
            @Override public boolean shouldOverrideUrlLoading(WebView source, String url) {
                return !nativeNavigation(handle, document.grant(), url, true, "GET");
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView source, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if ("overte-embedded.invalid".equals(request.getUrl().getHost())) {
                    byte[] data = nativeResource(handle, document.grant(), url);
                    String mime = nativeResourceMime(handle, document.grant(), url);
                    return data == null ? forbidden() : new WebResourceResponse(mime, "UTF-8", new ByteArrayInputStream(data));
                }
                return nativeNavigation(handle, document.grant(), url, request.isForMainFrame(), request.getMethod()) ? null : forbidden();
            }
            @Override public void onPageStarted(WebView source, String url, Bitmap favicon) {
                document.begin(document.grant()); loading = true;
                nativePage(handle, document.grant(), document.page(), url); publish();
            }
            @Override public void onPageFinished(WebView source, String url) {
                if (!active || !url.equals(view.getUrl())) return;
                loading = false; authorize(); publish();
            }
            @Override public void doUpdateVisitedHistory(WebView source, String url, boolean reload) { publish(); }
            @Override public void onReceivedSslError(WebView source, SslErrorHandler handler, SslError error) {
                handler.cancel(); status = LOAD_FAILED; loading = false; publish();
            }
            @Override public void onReceivedError(WebView source, android.webkit.WebResourceRequest request,
                                                 android.webkit.WebResourceError error) {
                if (request.isForMainFrame()) { status = LOAD_FAILED; loading = false; publish(); }
            }
            @Override public boolean onRenderProcessGone(WebView source, RenderProcessGoneDetail detail) { fail(RUNTIME_FAILED); return true; }
        };
        final WebChromeClient chrome = new WebChromeClient() {
            @Override public void onPermissionRequest(PermissionRequest request) { request.deny(); }
            @Override public void onGeolocationPermissionsShowPrompt(String origin, android.webkit.GeolocationPermissions.Callback callback) { callback.invoke(origin, false, false); }
            @Override public boolean onShowFileChooser(WebView source, ValueCallback<Uri[]> result, FileChooserParams request) {
                EmbeddedWebHost owner = host.get();
                long page = document.page(), lease = ++pickerLease;
                String sourceIdentity = requestedUrl, documentIdentity = view.getUrl();
                if (!visible || owner == null || !owner.isForeground()
                        || !nativeFileChooserAllowed(handle, document.grant(), page, documentIdentity)) { result.onReceiveValue(null); return true; }
                WebFileChoiceLease selected = new WebFileChoiceLease(Instance.this, owner, page, sourceIdentity, documentIdentity);
                ValueCallback<Uri[]> guarded = values -> {
                    int decision = selected.consume(Instance.this, host.get(), document.page(), requestedUrl, view.getUrl(),
                        lease == pickerLease, active, visible, owner.isForeground(),
                        nativeFileChooserAllowed(handle, document.grant(), document.page(), view.getUrl()));
                    if (decision == 0) return;
                    if (lease == pickerLease) ++pickerLease;
                    result.onReceiveValue(decision == 2 ? values : null);
                };
                if (!owner.chooseFiles(guarded, request)) { guarded.onReceiveValue(null); status = FILE_CHOOSER_UNAVAILABLE; publish(); }
                return true;
            }
        };
    }
    private static String origin(String url) {
        Uri target = Uri.parse(url);
        if (!"http".equals(target.getScheme()) && !"https".equals(target.getScheme())) return null;
        if (target.getHost() == null || target.getUserInfo() != null) return null;
        return target.getScheme() + "://" + target.getEncodedAuthority();
    }
    private static WebResourceResponse forbidden() {
        return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden", Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
    }
}
