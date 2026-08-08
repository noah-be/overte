package org.overte.pico;

import android.annotation.SuppressLint;
import android.graphics.Bitmap;
import android.graphics.Canvas;
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
import java.util.HashMap;
import java.util.Map;

/** Renders Android WebViews into buffers consumed by PicoWebViewItem. */
public final class OffscreenWebView {
    private static final String TAG = "OverteWebEntity";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final Map<Long, Instance> INSTANCES = new HashMap<>();
    private static final int FRAME_INTERVAL_MS = 100;
    private static final int MAX_TEXTURE_EDGE = 2048;

    private OffscreenWebView() { }

    private static native void nativeFrame(
        long nativeHandle, ByteBuffer pixels, int width, int height);

    @SuppressLint("SetJavaScriptEnabled")
    public static void create(long nativeHandle, int width, int height, String url,
                              String userAgent) {
        MAIN.post(() -> {
            destroyOnMain(nativeHandle);
            WebView view = new WebView(PicoInterfaceActivity.getInstance());
            view.setBackgroundColor(0x00000000);
            view.setLayerType(View.LAYER_TYPE_SOFTWARE, null);
            view.setWebViewClient(new WebViewClient() {
                @Override public void onPageFinished(WebView finishedView, String finishedUrl) {
                    Log.i(TAG, "Finished WebView page (URL length "
                        + (finishedUrl == null ? 0 : finishedUrl.length()) + ")");
                }
            });
            WebSettings settings = view.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setDomStorageEnabled(true);
            settings.setAllowFileAccess(true);
            settings.setAllowContentAccess(true);
            if (userAgent != null && !userAgent.isEmpty()) {
                settings.setUserAgentString(userAgent);
            }
            Instance instance = new Instance(nativeHandle, view);
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

    private static void destroyOnMain(long nativeHandle) {
        Instance old = INSTANCES.remove(nativeHandle);
        if (old != null) {
            old.active = false;
            MAIN.removeCallbacks(old.renderFrame);
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
                instance.view.loadUrl(url == null || url.isEmpty() ? "about:blank" : url);
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
            long now = android.os.SystemClock.uptimeMillis();
            MotionEvent event = MotionEvent.obtain(now, now, action, x, y, 0);
            if (action == MotionEvent.ACTION_HOVER_ENTER
                    || action == MotionEvent.ACTION_HOVER_MOVE
                    || action == MotionEvent.ACTION_HOVER_EXIT) {
                event.setSource(InputDevice.SOURCE_MOUSE);
                instance.view.dispatchGenericMotionEvent(event);
            } else {
                event.setSource(InputDevice.SOURCE_TOUCHSCREEN);
                instance.view.dispatchTouchEvent(event);
            }
            event.recycle();
        });
    }

    public static void scroll(long nativeHandle, float x, float y, float delta) {
        MAIN.post(() -> {
            Instance instance = INSTANCES.get(nativeHandle);
            if (instance == null) {
                return;
            }
            MotionEvent.PointerProperties properties = new MotionEvent.PointerProperties();
            properties.id = 0;
            properties.toolType = MotionEvent.TOOL_TYPE_MOUSE;
            MotionEvent.PointerCoords coords = new MotionEvent.PointerCoords();
            coords.x = x;
            coords.y = y;
            coords.setAxisValue(MotionEvent.AXIS_VSCROLL, delta);
            long now = android.os.SystemClock.uptimeMillis();
            MotionEvent event = MotionEvent.obtain(now, now, MotionEvent.ACTION_SCROLL,
                1, new MotionEvent.PointerProperties[] { properties },
                new MotionEvent.PointerCoords[] { coords }, 0, 0, 1.0f, 1.0f,
                0, 0, InputDevice.SOURCE_MOUSE, 0);
            instance.view.dispatchGenericMotionEvent(event);
            event.recycle();
        });
    }

    private static final class Instance {
        final long nativeHandle;
        final WebView view;
        boolean active = true;
        Bitmap bitmap;
        Canvas canvas;
        ByteBuffer pixels;
        boolean reportedFirstFrame;

        final Runnable renderFrame = new Runnable() {
            @Override public void run() {
                if (!active || bitmap == null) {
                    return;
                }
                bitmap.eraseColor(0x00000000);
                view.draw(canvas);
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

        Instance(long nativeHandle, WebView view) {
            this.nativeHandle = nativeHandle;
            this.view = view;
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
            pixels = ByteBuffer.allocateDirect(width * height * 4);
            int widthSpec = View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY);
            int heightSpec = View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY);
            view.measure(widthSpec, heightSpec);
            view.layout(0, 0, width, height);
        }
    }
}
