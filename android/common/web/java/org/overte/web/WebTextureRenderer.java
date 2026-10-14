// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

import android.app.Activity;
import android.app.Presentation;
import android.content.Context;
import android.graphics.Color;
import android.graphics.SurfaceTexture;
import android.graphics.drawable.ColorDrawable;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.opengl.EGL14;
import android.opengl.EGLConfig;
import android.opengl.EGLContext;
import android.opengl.EGLDisplay;
import android.opengl.EGLSurface;
import android.opengl.GLES11Ext;
import android.opengl.GLES20;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.SystemClock;
import android.view.Surface;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.WebView;
import android.widget.FrameLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.util.concurrent.atomic.AtomicBoolean;

/** Chromium's supported snapshot path: an attached hardware WebView on an app-owned display. */
final class WebTextureRenderer implements AutoCloseable {
    interface Callback {
        void ready(WebTextureRenderer renderer);
        void resized();
        void frame(WebFrameGate.Ticket ticket, ByteBuffer pixels, int width, int height);
        void failed();
    }
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final Object DISPLAY_LOCK = new Object();
    private final Activity activity;
    private final Callback callback;
    private final WebFrameGate gate;
    private final HandlerThread thread = new HandlerThread("OverteWebTexture");
    private final Handler gl;
    private final AtomicBoolean closed = new AtomicBoolean();
    private VirtualDisplay display;
    private Presentation presentation;
    private FrameLayout container;
    private WebView attached;
    private int width, height;
    private long surfaceEpoch = 1, lastCapture;
    private boolean busy, signal, surfaceReady, retryScheduled, surfaceActive = true;
    private final Runnable retryCapture = () -> { retryScheduled = false; signal = true; schedule(); };
    // These resources are exclusively created/used/released by the GL handler.
    private EGLDisplay eglDisplay = EGL14.EGL_NO_DISPLAY;
    private EGLContext eglContext = EGL14.EGL_NO_CONTEXT;
    private EGLSurface eglSurface = EGL14.EGL_NO_SURFACE;
    private SurfaceTexture texture;
    private Surface surface;
    private int oes, color, fbo, program;
    private ByteBuffer rgba, packed;
    private final FloatBuffer vertices = ByteBuffer.allocateDirect(16 * 4).order(ByteOrder.nativeOrder()).asFloatBuffer();
    private final float[] matrix = new float[16];

    WebTextureRenderer(Activity activity, int width, int height, Callback callback) {
        this.activity = activity; this.callback = callback; this.gate = new WebFrameGate(activity);
        int[] size = size(width, height); this.width = size[0]; this.height = size[1];
        vertices.put(new float[]{-1,-1,0,0, 1,-1,1,0, -1,1,0,1, 1,1,1,1}).position(0);
        thread.start(); gl = new Handler(thread.getLooper());
        gl.post(() -> {
            try { initialize(); MAIN.post(this::present); }
            catch (RuntimeException | OutOfMemoryError failure) { fail(); }
        });
    }
    private static int[] size(int width, int height) {
        if (width < 1 || height < 1) throw new IllegalArgumentException("invalid viewport");
        double ratio = Math.min(1.0, 2048.0 / Math.max(width, height));
        return new int[]{Math.max(1,(int)Math.round(width * ratio)), Math.max(1,(int)Math.round(height * ratio))};
    }
    Context context() { return presentation.getContext(); }
    void attach(WebView view) {
        attached = view;
        container.addView(view, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }
    private void present() {
        if (closed.get()) return;
        try {
            DisplayManager manager = (DisplayManager) activity.getSystemService(Context.DISPLAY_SERVICE);
            // No PUBLIC, AUTO_MIRROR or SECURE flag: capture only this app's own window.
            display = manager.createVirtualDisplay("OverteWeb", width, height, 160, surface,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY | DisplayManager.VIRTUAL_DISPLAY_FLAG_PRESENTATION);
            if (display == null) throw new IllegalStateException("display unavailable");
            showPresentation(); surfaceReady = true; callback.ready(this);
        } catch (RuntimeException | OutOfMemoryError failure) { fail(); }
    }
    private void showPresentation() {
        presentation = new Presentation(activity, display.getDisplay());
        presentation.getWindow().addFlags(WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED
            | WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL);
        presentation.getWindow().setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
        container = new FrameLayout(presentation.getContext());
        presentation.requestWindowFeature(Window.FEATURE_NO_TITLE);
        presentation.setContentView(container); presentation.show();
        presentation.getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT);
        if (attached != null) container.addView(attached,new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
    }
    void resize(int requestedWidth, int requestedHeight) {
        int[] size = size(requestedWidth, requestedHeight);
        if (closed.get() || (size[0] == width && size[1] == height)) return;
        width = size[0]; height = size[1]; final int w = width, h = height;
        final long epoch = ++surfaceEpoch; surfaceReady = false; gate.invalidate();
        gl.post(() -> {
            if (closed.get()) return;
            try {
                texture.setDefaultBufferSize(w,h); allocate(w,h);
                MAIN.post(() -> {
                    if (closed.get() || epoch != surfaceEpoch) return;
                    try {
                        // Presentation cancels itself when display metrics change. Recreate only
                        // its window; preserve the existing document and its native editor focus.
                        boolean focused = attached != null && attached.hasFocus();
                        if (attached != null) container.removeView(attached);
                        presentation.dismiss(); display.resize(w,h,160); showPresentation();
                        if (focused) attached.requestFocus();
                        surfaceReady = true; callback.resized();
                    }
                    catch (RuntimeException failure) { fail(); }
                });
            } catch (RuntimeException | OutOfMemoryError failure) { fail(); }
        });
    }
    void invalidate() { gate.invalidate(); }
    void pause() {
        gate.invalidate(); surfaceActive = false;
        try { if (display != null) display.setSurface(null); } catch (RuntimeException failure) { fail(); }
    }
    void resume() {
        if (closed.get() || surfaceActive) return;
        try { display.setSurface(surface); surfaceActive = true; } catch (RuntimeException failure) { fail(); }
    }
    void arm(WebView view, long grant, long page, String document) {
        if (closed.get() || !surfaceReady || !surfaceActive || gate.matches(grant,page,surfaceEpoch,document)) return;
        WebFrameGate.Ticket ticket = gate.begin(activity,grant,page,surfaceEpoch,document);
        if (ticket == null) return;
        view.postVisualStateCallback(ticket.serial, new WebView.VisualStateCallback() {
            @Override public void onComplete(long requestId) {
                if (closed.get() || requestId != ticket.serial || !gate.matches(grant,page,ticket.surface,document)) return;
                if (!view.isHardwareAccelerated()) { fail(); return; }
                // The callback promises the NEXT draw reflects the requested DOM state.
                // Drain queued buffers first, then invalidate and require a newer producer timestamp.
                gl.post(() -> {
                    if (closed.get()) return;
                    try {
                        texture.updateTexImage(); final long baseline = texture.getTimestamp();
                        MAIN.post(() -> {
                            if (!closed.get() && gate.visual(ticket,baseline)) view.invalidate();
                        });
                    } catch (RuntimeException failure) { fail(); }
                });
            }
        });
    }
    private void onSignal() { if (!closed.get()) { signal = true; schedule(); } }
    private void schedule() {
        if (closed.get() || busy || !signal) return;
        signal = false; busy = true;
        WebFrameGate.Ticket ticket = gate.capture();
        long now = SystemClock.uptimeMillis();
        boolean capture = ticket != null && now - lastCapture >= 100;
        if (capture) lastCapture = now;
        final boolean copy = capture; final int w = width, h = height; final long epoch = surfaceEpoch;
        gl.post(() -> {
            ByteBuffer result = null; long timestamp = 0;
            try {
                if (!closed.get()) {
                    // Drain even before the visual barrier, preventing BufferQueue backpressure.
                    texture.updateTexImage();
                    timestamp = texture.getTimestamp();
                    if (copy && gate.fresh(ticket,timestamp)) { texture.getTransformMatrix(matrix); draw(w,h); result = packed; }
                }
            } catch (RuntimeException | OutOfMemoryError failure) { fail(); }
            final ByteBuffer pixels = result; final long produced = timestamp;
            MAIN.post(() -> {
                if (!closed.get() && epoch == surfaceEpoch && gate.fresh(ticket,produced)) {
                    if (pixels != null && gate.deliver(ticket,produced)) {
                        lastCapture = SystemClock.uptimeMillis(); callback.frame(ticket,pixels,w,h);
                    } else if (!retryScheduled) {
                        retryScheduled = true; MAIN.postDelayed(retryCapture,Math.max(1,100-(SystemClock.uptimeMillis()-lastCapture)));
                    }
                }
                busy = false; if (!closed.get() && signal) schedule();
            });
        });
    }
    private void fail() {
        MAIN.post(() -> { if (!closed.get()) { close(); callback.failed(); } });
    }
    @Override public void close() {
        if (!closed.compareAndSet(false,true)) return;
        gate.close(); MAIN.removeCallbacks(retryCapture);
        if (attached != null && container != null) { container.removeView(attached); attached = null; }
        if (presentation != null) { try { presentation.dismiss(); } catch (RuntimeException ignored) { } }
        if (display != null) display.release();
        gl.post(() -> { try { release(); } finally { thread.quitSafely(); } });
    }
    private void initialize() {
        synchronized (DISPLAY_LOCK) {
            EGLDisplay candidate = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY);
            int[] version = new int[2];
            if (candidate == EGL14.EGL_NO_DISPLAY || !EGL14.eglInitialize(candidate,version,0,version,1)) throw new IllegalStateException();
            eglDisplay = candidate;
        }
        int[] attributes = {EGL14.EGL_SURFACE_TYPE,EGL14.EGL_PBUFFER_BIT,EGL14.EGL_RENDERABLE_TYPE,EGL14.EGL_OPENGL_ES2_BIT,
            EGL14.EGL_RED_SIZE,8,EGL14.EGL_GREEN_SIZE,8,EGL14.EGL_BLUE_SIZE,8,EGL14.EGL_ALPHA_SIZE,8,EGL14.EGL_NONE};
        EGLConfig[] configs = new EGLConfig[1]; int[] count = new int[1];
        if (!EGL14.eglChooseConfig(eglDisplay,attributes,0,configs,0,1,count,0) || count[0] < 1) throw new IllegalStateException();
        eglContext = EGL14.eglCreateContext(eglDisplay,configs[0],EGL14.EGL_NO_CONTEXT,new int[]{EGL14.EGL_CONTEXT_CLIENT_VERSION,2,EGL14.EGL_NONE},0);
        eglSurface = EGL14.eglCreatePbufferSurface(eglDisplay,configs[0],new int[]{EGL14.EGL_WIDTH,1,EGL14.EGL_HEIGHT,1,EGL14.EGL_NONE},0);
        if (eglContext == EGL14.EGL_NO_CONTEXT || eglSurface == EGL14.EGL_NO_SURFACE
            || !EGL14.eglMakeCurrent(eglDisplay,eglSurface,eglSurface,eglContext)) throw new IllegalStateException();
        int[] id = new int[1]; GLES20.glGenTextures(1,id,0); oes = id[0];
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,oes);
        parameters(GLES11Ext.GL_TEXTURE_EXTERNAL_OES);
        texture = new SurfaceTexture(oes); texture.setDefaultBufferSize(width,height);
        texture.setOnFrameAvailableListener(ignored -> onSignal(),MAIN); surface = new Surface(texture);
        int vertex = shader(GLES20.GL_VERTEX_SHADER,"attribute vec2 position;attribute vec2 coordinate;uniform mat4 matrix;varying vec2 uv;void main(){gl_Position=vec4(position,0.,1.);uv=(matrix*vec4(coordinate,0.,1.)).xy;}");
        int fragment = shader(GLES20.GL_FRAGMENT_SHADER,"#extension GL_OES_EGL_image_external : require\nprecision mediump float;uniform samplerExternalOES source;varying vec2 uv;void main(){gl_FragColor=texture2D(source,uv);}");
        program = GLES20.glCreateProgram(); GLES20.glAttachShader(program,vertex); GLES20.glAttachShader(program,fragment); GLES20.glLinkProgram(program);
        GLES20.glDeleteShader(vertex); GLES20.glDeleteShader(fragment);
        GLES20.glGetProgramiv(program,GLES20.GL_LINK_STATUS,id,0); if (id[0] == 0) throw new IllegalStateException();
        allocate(width,height); checkGl();
    }
    private static int shader(int type, String source) {
        int shader = GLES20.glCreateShader(type); GLES20.glShaderSource(shader,source); GLES20.glCompileShader(shader);
        int[] status = new int[1]; GLES20.glGetShaderiv(shader,GLES20.GL_COMPILE_STATUS,status,0);
        if (status[0] == 0) { GLES20.glDeleteShader(shader); throw new IllegalStateException(); } return shader;
    }
    private static void parameters(int target) {
        GLES20.glTexParameteri(target,GLES20.GL_TEXTURE_MIN_FILTER,GLES20.GL_LINEAR);
        GLES20.glTexParameteri(target,GLES20.GL_TEXTURE_MAG_FILTER,GLES20.GL_LINEAR);
        GLES20.glTexParameteri(target,GLES20.GL_TEXTURE_WRAP_S,GLES20.GL_CLAMP_TO_EDGE);
        GLES20.glTexParameteri(target,GLES20.GL_TEXTURE_WRAP_T,GLES20.GL_CLAMP_TO_EDGE);
    }
    private void allocate(int w, int h) {
        if (color != 0) GLES20.glDeleteTextures(1,new int[]{color},0);
        if (fbo != 0) GLES20.glDeleteFramebuffers(1,new int[]{fbo},0);
        int[] id = new int[1]; GLES20.glGenTextures(1,id,0); color = id[0]; GLES20.glBindTexture(GLES20.GL_TEXTURE_2D,color);
        parameters(GLES20.GL_TEXTURE_2D); GLES20.glTexImage2D(GLES20.GL_TEXTURE_2D,0,GLES20.GL_RGBA,w,h,0,GLES20.GL_RGBA,GLES20.GL_UNSIGNED_BYTE,null);
        GLES20.glGenFramebuffers(1,id,0); fbo = id[0]; GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER,fbo);
        GLES20.glFramebufferTexture2D(GLES20.GL_FRAMEBUFFER,GLES20.GL_COLOR_ATTACHMENT0,GLES20.GL_TEXTURE_2D,color,0);
        if (GLES20.glCheckFramebufferStatus(GLES20.GL_FRAMEBUFFER) != GLES20.GL_FRAMEBUFFER_COMPLETE) throw new IllegalStateException();
        rgba = ByteBuffer.allocateDirect(w*h*4); packed = ByteBuffer.allocateDirect(w*h*4); checkGl();
    }
    private void draw(int w, int h) {
        GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER,fbo); GLES20.glViewport(0,0,w,h); GLES20.glUseProgram(program);
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0); GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,oes);
        GLES20.glUniform1i(GLES20.glGetUniformLocation(program,"source"),0);
        GLES20.glUniformMatrix4fv(GLES20.glGetUniformLocation(program,"matrix"),1,false,matrix,0);
        int position = GLES20.glGetAttribLocation(program,"position"), coordinate = GLES20.glGetAttribLocation(program,"coordinate");
        vertices.position(0); GLES20.glVertexAttribPointer(position,2,GLES20.GL_FLOAT,false,16,vertices); GLES20.glEnableVertexAttribArray(position);
        vertices.position(2); GLES20.glVertexAttribPointer(coordinate,2,GLES20.GL_FLOAT,false,16,vertices); GLES20.glEnableVertexAttribArray(coordinate);
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP,0,4); rgba.position(0);
        GLES20.glReadPixels(0,0,w,h,GLES20.GL_RGBA,GLES20.GL_UNSIGNED_BYTE,rgba); checkGl();
        WebFramePixels.pack(rgba,packed,w,h,w*4,4);
    }
    private static void checkGl() { if (GLES20.glGetError() != GLES20.GL_NO_ERROR) throw new IllegalStateException("GL capture failed"); }
    private void release() {
        if (surface != null) { surface.release(); surface = null; }
        if (texture != null) { texture.release(); texture = null; }
        if (eglDisplay != EGL14.EGL_NO_DISPLAY) {
            if (eglContext != EGL14.EGL_NO_CONTEXT) {
                EGL14.eglMakeCurrent(eglDisplay,eglSurface,eglSurface,eglContext);
                if (oes != 0) GLES20.glDeleteTextures(1,new int[]{oes},0);
                if (color != 0) GLES20.glDeleteTextures(1,new int[]{color},0);
                if (fbo != 0) GLES20.glDeleteFramebuffers(1,new int[]{fbo},0);
                if (program != 0) GLES20.glDeleteProgram(program);
            }
            EGL14.eglMakeCurrent(eglDisplay,EGL14.EGL_NO_SURFACE,EGL14.EGL_NO_SURFACE,EGL14.EGL_NO_CONTEXT);
            if (eglSurface != EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(eglDisplay,eglSurface);
            if (eglContext != EGL14.EGL_NO_CONTEXT) EGL14.eglDestroyContext(eglDisplay,eglContext);
            // Qt and other views also own contexts on Android's process-wide default display.
            // Retire only our context/surface; never eglTerminate that shared native display.
            eglDisplay = EGL14.EGL_NO_DISPLAY; EGL14.eglReleaseThread();
        }
        rgba = null; packed = null;
    }
}
