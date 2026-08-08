package org.overte.pico;

import android.annotation.SuppressLint;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.View;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** Renders Android WebViews into buffers consumed by PicoWebViewItem. */
public final class OffscreenWebView {
    private static final String TAG = "OverteWebEntity";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final Map<Long, Instance> INSTANCES = new HashMap<>();
    private static final int FRAME_INTERVAL_MS = 100;
    private static final int MAX_TEXTURE_EDGE = 2048;
    private static boolean wholeDocumentDrawEnabled;

    private OffscreenWebView() { }

    private static native void nativeFrame(
        long nativeHandle, ByteBuffer pixels, int width, int height);

    @SuppressLint("SetJavaScriptEnabled")
    public static void create(long nativeHandle, int width, int height, String url,
                              String userAgent, boolean useBackground) {
        MAIN.post(() -> {
            destroyOnMain(nativeHandle);
            PicoInterfaceActivity activity = PicoInterfaceActivity.getInstance();
            if (activity == null) {
                Log.e(TAG, "Cannot create offscreen WebView: Activity is unavailable");
                return;
            }
            final WebView view;
            try {
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
            } catch (RuntimeException exception) {
                Log.e(TAG, "Cannot create offscreen WebView", exception);
                return;
            }
            view.setBackgroundColor(useBackground ? Color.WHITE : Color.TRANSPARENT);
            view.setLayerType(View.LAYER_TYPE_SOFTWARE, null);
            view.setWebViewClient(new WebViewClient() {
                @Override public void onPageFinished(WebView finishedView, String finishedUrl) {
                    finishedView.scrollTo(0, 0);
                    Log.i(TAG, "Finished WebView page (URL length "
                        + (finishedUrl == null ? 0 : finishedUrl.length()) + ")");
                }
            });
            WebSettings settings = view.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setDomStorageEnabled(true);
            settings.setUseWideViewPort(true);
            settings.setAllowFileAccess(true);
            settings.setAllowContentAccess(true);
            if (userAgent != null && !userAgent.isEmpty()) {
                settings.setUserAgentString(userAgent);
            }
            float displayDensity = activity.getResources().getDisplayMetrics().density;
            Instance instance = new Instance(nativeHandle, view, displayDensity);
            INSTANCES.put(nativeHandle, instance);
            instance.resize(width, height);
            view.loadUrl(url == null || url.isEmpty() ? "about:blank" : url);
            Log.i(TAG, "Created offscreen WebView " + width + "x" + height);
            MAIN.post(instance.renderFrame);
        });
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

    private static void destroyOnMain(long nativeHandle) {
        Instance old = INSTANCES.remove(nativeHandle);
        if (old != null) {
            old.active = false;
            MAIN.removeCallbacks(old.renderFrame);
            old.cancelActiveTouch();
            old.view.stopLoading();
            old.view.loadUrl("about:blank");
            old.view.destroy();
            Log.i(TAG, "Destroyed offscreen WebView");
        }
    }

    public static void load(long nativeHandle, String url) {
        MAIN.post(() -> {
            Instance instance = INSTANCES.get(nativeHandle);
            if (instance != null) {
                instance.cancelActiveTouch();
                instance.pendingScroll = 0.0f;
                instance.view.loadUrl(url == null || url.isEmpty() ? "about:blank" : url);
            }
        });
    }

    public static void setUseBackground(long nativeHandle, boolean useBackground) {
        MAIN.post(() -> {
            Instance instance = INSTANCES.get(nativeHandle);
            if (instance != null) {
                instance.view.setBackgroundColor(
                    useBackground ? Color.WHITE : Color.TRANSPARENT);
                instance.view.invalidate();
            }
        });
    }

    public static void resize(long nativeHandle, int width, int height) {
        MAIN.post(() -> {
            Instance instance = INSTANCES.get(nativeHandle);
            if (instance != null) {
                instance.resize(width, height);
            }
        });
    }

    public static void pointer(long nativeHandle, int action, float x, float y) {
        MAIN.post(() -> {
            Instance instance = INSTANCES.get(nativeHandle);
            if (instance == null) {
                return;
            }
            instance.dispatchPointer(action, x, y);
        });
    }

    public static void scroll(long nativeHandle, float x, float y, float delta) {
        MAIN.post(() -> {
            Instance instance = INSTANCES.get(nativeHandle);
            if (instance == null) {
                return;
            }
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
                instance.refreshLayout();
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
                bitmap.eraseColor(0x00000000);
                int saveCount = canvas.save();
                canvas.translate(-view.getScrollX(), -view.getScrollY());
                view.draw(canvas);
                canvas.restoreToCount(saveCount);
                pixels.rewind();
                bitmap.copyPixelsToBuffer(pixels);
                pixels.rewind();
                nativeFrame(nativeHandle, pixels, bitmap.getWidth(), bitmap.getHeight());
                if (!reportedFirstFrame) {
                    reportedFirstFrame = true;
                    Log.i(TAG, "Delivered first WebView frame "
                        + bitmap.getWidth() + "x" + bitmap.getHeight());
                }
                MAIN.postDelayed(this, FRAME_INTERVAL_MS);
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

        void resize(int requestedWidth, int requestedHeight) {
            int width = Math.max(1, requestedWidth);
            int height = Math.max(1, requestedHeight);
            int longestEdge = Math.max(width, height);
            if (longestEdge > MAX_TEXTURE_EDGE) {
                float scale = (float) MAX_TEXTURE_EDGE / longestEdge;
                width = Math.max(1, Math.round(width * scale));
                height = Math.max(1, Math.round(height * scale));
            }
            if (bitmap != null && bitmap.getWidth() == width && bitmap.getHeight() == height) {
                return;
            }
            bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
            canvas = new Canvas(bitmap);
            canvas.scale(1.0f / displayDensity, 1.0f / displayDensity);
            pixels = ByteBuffer.allocateDirect(width * height * 4);
            int layoutWidth = Math.max(1, Math.round(width * displayDensity));
            int layoutHeight = Math.max(1, Math.round(height * displayDensity));
            int widthSpec = View.MeasureSpec.makeMeasureSpec(layoutWidth, View.MeasureSpec.EXACTLY);
            int heightSpec = View.MeasureSpec.makeMeasureSpec(layoutHeight, View.MeasureSpec.EXACTLY);
            view.measure(widthSpec, heightSpec);
            view.layout(0, 0, layoutWidth, layoutHeight);
        }
    }
}
