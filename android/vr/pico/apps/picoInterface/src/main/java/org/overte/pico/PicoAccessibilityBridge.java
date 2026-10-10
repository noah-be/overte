package org.overte.pico;

import android.app.Activity;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.os.Process;
import android.system.Os;
import android.system.ErrnoException;
import android.util.AtomicFile;
import android.view.SurfaceView;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityNodeProvider;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/** Publishes the rendered Qt Quick items through Android's native view tree. */
final class PicoAccessibilityBridge {
    private static final int HOST = AccessibilityNodeProvider.HOST_VIEW_ID;
    private static final long MAX_FRAME_AGE_MS = 1000;
    private static native boolean nativeRequestFrame(PicoAccessibilityBridge receiver,
                                                    int width, int height, int generation);
    private static native boolean nativePerformAction(int identifier, String action, String text);
    private final Activity activity;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final AccessibilityManager manager;
    private final Map<Integer, JSONObject> nodes = new HashMap<>();
    private final Runnable tick = this::refresh;
    private View surface;
    private boolean running;
    private boolean requestPending;
    private int generation;
    private int accessibilityFocus = HOST;
    private long receivedAt;
    private boolean controlledDebugProbe;
    private long lastDiagnosticAt;
    private long acceptedFrames;
    private long hostQueries;
    private long virtualQueries;
    private long missingQueries;
    private final AccessibilityNodeProvider provider = new Provider();
    private final View.AccessibilityDelegate delegate = new View.AccessibilityDelegate() {
        @Override public AccessibilityNodeProvider getAccessibilityNodeProvider(View host) {
            return provider;
        }
    };

    PicoAccessibilityBridge(Activity activity) {
        this.activity = activity;
        manager = (AccessibilityManager) activity.getSystemService(Activity.ACCESSIBILITY_SERVICE);
    }

    void start() {
        if (running) { return; }
        running = true;
        ++generation;
        handler.post(tick);
    }

    void stop() {
        running = false;
        ++generation;
        requestPending = false;
        nodes.clear();
        accessibilityFocus = HOST;
        writeDiagnostic(true);
        handler.removeCallbacks(tick);
        if (surface != null) { surface.setAccessibilityDelegate(null); }
        surface = null;
    }

    private View renderSurface(View view) {
        if (view instanceof SurfaceView && view.isShown() && view.getWidth() > 0 && view.getHeight() > 0) {
            return view;
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); ++i) {
                View found = renderSurface(group.getChildAt(i));
                if (found != null) { return found; }
            }
        }
        return null;
    }

    private void refresh() {
        if (!running) { return; }
        if (manager != null && manager.isEnabled()) {
            View actual = renderSurface(activity.getWindow().getDecorView());
            if (actual != surface) {
                if (surface != null) { surface.setAccessibilityDelegate(null); }
                surface = actual;
                ++generation;
                requestPending = false;
                nodes.clear();
                accessibilityFocus = HOST;
                if (surface != null) {
                    surface.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
                    surface.setAccessibilityDelegate(delegate);
                }
            }
            if (surface != null && !requestPending) {
                try {
                    requestPending = nativeRequestFrame(this, surface.getWidth(), surface.getHeight(), generation);
                } catch (UnsatisfiedLinkError startup) {
                    // The Java Activity can resume before the native library is ready.
                }
            }
        } else {
            nodes.clear();
        }
        handler.postDelayed(tick, 250);
        writeDiagnostic(false);
    }

    // Private read-only state, enabled only by the canonical native test probe.
    // Publishing accessibility nodes and their freshness does not depend on it.
    private void writeDiagnostic(boolean force) {
        long now = SystemClock.uptimeMillis();
        if (!controlledDebugProbe || (!force && now - lastDiagnosticAt < 1000)) { return; }
        lastDiagnosticAt = now;
        AtomicFile output = new AtomicFile(new File(activity.getFilesDir(),
            "overte-e2e/accessibility-bridge-observation.json"));
        FileOutputStream stream = null;
        try {
            JSONObject state = new JSONObject();
            state.put("schemaVersion", 1);
            state.put("source", "actual-android-accessibility-bridge");
            state.put("processId", Process.myPid());
            state.put("updatedEpochMs", System.currentTimeMillis());
            state.put("running", running);
            state.put("managerEnabled", manager != null && manager.isEnabled());
            state.put("requestPending", requestPending);
            state.put("generation", generation);
            state.put("acceptedFrames", acceptedFrames);
            state.put("nodeCount", nodes.size());
            state.put("frameAgeMs", receivedAt == 0 ? -1 : now - receivedAt);
            state.put("frameFresh", fresh());
            state.put("hostQueries", hostQueries);
            state.put("virtualQueries", virtualQueries);
            state.put("missingQueries", missingQueries);
            state.put("windowFocused", activity.getWindow().getDecorView().hasWindowFocus());
            state.put("surfaceFound", surface != null);
            JSONArray ancestors = new JSONArray();
            View current = surface;
            for (int depth = 0; current != null && depth < 8; ++depth) {
                JSONObject view = new JSONObject();
                view.put("className", current.getClass().getName());
                view.put("shown", current.isShown());
                view.put("importance", current.getImportantForAccessibility());
                view.put("width", current.getWidth());
                view.put("height", current.getHeight());
                view.put("displayId", current.getDisplay() == null ? -1 : current.getDisplay().getDisplayId());
                if (depth == 0) view.put("providerAttached", current.getAccessibilityNodeProvider() == provider);
                ancestors.put(view);
                current = current.getParent() instanceof View ? (View) current.getParent() : null;
            }
            state.put("ancestors", ancestors);
            JSONArray semanticIds = new JSONArray();
            for (JSONObject node : nodes.values()) {
                String semantic = node.optString("semanticId");
                if (!semantic.isEmpty()) semanticIds.put(semantic);
            }
            state.put("semanticIds", semanticIds);
            stream = output.startWrite();
            Os.fchmod(stream.getFD(), 0600);
            stream.write(state.toString().getBytes(StandardCharsets.UTF_8));
            output.finishWrite(stream);
        } catch (JSONException | IOException | ErrnoException unavailable) {
            if (stream != null) output.failWrite(stream);
            // Diagnostic failures cannot change the live provider's behavior.
        }
    }

    // Native Qt GUI delivery is asynchronous; Android never waits for Qt's GUI.
    @SuppressWarnings("unused")
    private void acceptFrame(String content, int requestedGeneration) {
        handler.post(() -> {
            if (!running || requestedGeneration != generation) { return; }
            requestPending = false;
            Map<Integer, JSONObject> next = new HashMap<>();
            try {
                JSONObject frame = new JSONObject(content);
                controlledDebugProbe = frame.optBoolean("controlledDebugProbe", false);
                if (frame.getInt("schemaVersion") != 1 || !frame.getBoolean("ready") || surface == null
                        || frame.getInt("surfaceWidth") != surface.getWidth()
                        || frame.getInt("surfaceHeight") != surface.getHeight()) { nodes.clear(); return; }
                JSONArray source = frame.getJSONArray("nodes");
                if (source.length() > 1024) { nodes.clear(); return; }
                for (int index = 0; index < source.length(); ++index) {
                    JSONObject node = source.getJSONObject(index);
                    int id = node.getInt("id");
                    if (id == HOST || next.put(id, node) != null) { nodes.clear(); return; }
                }
                for (JSONObject node : next.values()) {
                    int parent = node.getInt("parentId");
                    if (parent != HOST && !next.containsKey(parent)) { nodes.clear(); return; }
                }
            } catch (JSONException invalid) { nodes.clear(); return; }
            // Emit changes only for actual native node content, not sample timestamps.
            boolean changed = !next.toString().equals(nodes.toString());
            nodes.clear();
            nodes.putAll(next);
            receivedAt = SystemClock.uptimeMillis();
            ++acceptedFrames;
            if (!nodes.containsKey(accessibilityFocus)) { accessibilityFocus = HOST; }
            if (changed) { event(HOST, AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED); }
        });
    }

    private boolean fresh() {
        return running && surface != null && surface.isShown()
                && SystemClock.uptimeMillis() - receivedAt <= MAX_FRAME_AGE_MS;
    }

    private void event(int id, int type) {
        if (surface == null || surface.getParent() == null || manager == null || !manager.isEnabled()) { return; }
        AccessibilityEvent event = AccessibilityEvent.obtain(type);
        event.setPackageName(activity.getPackageName());
        event.setClassName("android.view.View");
        event.setSource(surface, id);
        if (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) {
            event.setContentChangeTypes(AccessibilityEvent.CONTENT_CHANGE_TYPE_SUBTREE);
        }
        surface.getParent().requestSendAccessibilityEvent(surface, event);
    }

    private final class Provider extends AccessibilityNodeProvider {
        @Override public AccessibilityNodeInfo createAccessibilityNodeInfo(int id) {
            if (id == HOST) { ++hostQueries; } else { ++virtualQueries; }
            if (surface == null) { ++missingQueries; return null; }
            AccessibilityNodeInfo result = AccessibilityNodeInfo.obtain();
            result.setPackageName(activity.getPackageName());
            result.setSource(surface, id);
            if (id == HOST) {
                result.setClassName("android.view.View");
                result.setVisibleToUser(surface.isShown());
                result.setEnabled(surface.isEnabled());
                if (surface.getParent() instanceof View) { result.setParent((View) surface.getParent()); }
                int[] location = new int[2];
                surface.getLocationOnScreen(location);
                result.setBoundsInParent(new Rect(0, 0, surface.getWidth(), surface.getHeight()));
                result.setBoundsInScreen(new Rect(location[0], location[1],
                        location[0] + surface.getWidth(), location[1] + surface.getHeight()));
            } else {
                JSONObject node = fresh() ? nodes.get(id) : null;
                if (node == null) { ++missingQueries; result.recycle(); return null; }
                int parent = node.optInt("parentId", HOST);
                result.setParent(surface, parent);
                result.setClassName(node.optString("className", "android.view.View"));
                String semantic = node.optString("semanticId");
                if (!semantic.isEmpty()) { result.setViewIdResourceName(activity.getPackageName() + ":id/" + semantic); }
                result.setContentDescription(node.optString("name"));
                result.setText(node.optString("text"));
                result.setEnabled(node.optBoolean("enabled"));
                result.setFocusable(node.optBoolean("focusable"));
                result.setFocused(node.optBoolean("focused"));
                result.setEditable(node.optBoolean("editable"));
                result.setPassword(node.optBoolean("password"));
                result.setCheckable(node.optBoolean("checkable"));
                result.setChecked(node.optBoolean("checked"));
                result.setClickable(node.optBoolean("clickable"));
                result.setVisibleToUser(true);
                result.setAccessibilityFocused(accessibilityFocus == id);
                Rect bounds = new Rect((int) Math.floor(node.optDouble("left")),
                        (int) Math.floor(node.optDouble("top")), (int) Math.ceil(node.optDouble("right")),
                        (int) Math.ceil(node.optDouble("bottom")));
                int[] location = new int[2];
                surface.getLocationOnScreen(location);
                Rect parentBounds = new Rect(bounds);
                JSONObject parentNode = nodes.get(parent);
                if (parentNode != null) {
                    parentBounds.offset(-(int) Math.floor(parentNode.optDouble("left")),
                            -(int) Math.floor(parentNode.optDouble("top")));
                }
                result.setBoundsInParent(parentBounds);
                bounds.offset(location[0], location[1]);
                result.setBoundsInScreen(bounds);
                result.addAction(accessibilityFocus == id ? AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS
                                                        : AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS);
                if (node.optBoolean("enabled")) {
                    if (node.optBoolean("clickable")) { result.addAction(AccessibilityNodeInfo.ACTION_CLICK); }
                    if (node.optBoolean("focusable")) { result.addAction(AccessibilityNodeInfo.ACTION_FOCUS); }
                    if (node.optBoolean("editable")) { result.addAction(AccessibilityNodeInfo.ACTION_SET_TEXT); }
                }
            }
            if (fresh()) {
                for (JSONObject child : nodes.values()) {
                    if (child.optInt("parentId", HOST) == id) { result.addChild(surface, child.optInt("id")); }
                }
            }
            return result;
        }

        @Override public AccessibilityNodeInfo findFocus(int focus) {
            if (!fresh()) { return null; }
            if (focus == AccessibilityNodeInfo.FOCUS_ACCESSIBILITY) {
                return accessibilityFocus == HOST ? null : createAccessibilityNodeInfo(accessibilityFocus);
            }
            for (JSONObject node : nodes.values()) {
                if (node.optBoolean("focused")) { return createAccessibilityNodeInfo(node.optInt("id")); }
            }
            return null;
        }

        @Override public List<AccessibilityNodeInfo> findAccessibilityNodeInfosByText(String text, int id) {
            List<AccessibilityNodeInfo> result = new ArrayList<>();
            if (!fresh() || text == null) { return result; }
            for (JSONObject node : nodes.values()) {
                if (id != HOST) {
                    int ancestor = node.optInt("id");
                    int remaining = nodes.size() + 1;
                    while (ancestor != id && ancestor != HOST && remaining-- > 0) {
                        JSONObject parent = nodes.get(ancestor);
                        ancestor = parent == null ? HOST : parent.optInt("parentId", HOST);
                    }
                    if (ancestor != id) { continue; }
                }
                if (node.optString("name").contains(text) || node.optString("text").contains(text)) {
                    AccessibilityNodeInfo found = createAccessibilityNodeInfo(node.optInt("id"));
                    if (found != null) { result.add(found); }
                }
            }
            return result;
        }

        @Override public boolean performAction(int id, int action, Bundle arguments) {
            JSONObject node = fresh() ? nodes.get(id) : null;
            if (node == null || !node.optBoolean("enabled")) { return false; }
            if (action == AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS) {
                if (accessibilityFocus != HOST && accessibilityFocus != id) {
                    event(accessibilityFocus, AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUS_CLEARED);
                }
                accessibilityFocus = id;
                event(id, AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUSED);
                return true;
            }
            if (action == AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS) {
                if (accessibilityFocus != id) { return false; }
                accessibilityFocus = HOST;
                event(id, AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUS_CLEARED);
                return true;
            }
            String operation;
            String text = "";
            if (action == AccessibilityNodeInfo.ACTION_CLICK && node.optBoolean("clickable")) { operation = "press"; }
            else if (action == AccessibilityNodeInfo.ACTION_FOCUS && node.optBoolean("focusable")) { operation = "focus"; }
            else if (action == AccessibilityNodeInfo.ACTION_SET_TEXT && node.optBoolean("editable") && arguments != null) {
                CharSequence value = arguments.getCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE);
                if (value == null || value.length() > 4096) { return false; }
                operation = "set-text";
                text = value.toString();
            } else { return false; }
            try { return nativePerformAction(id, operation, text); }
            catch (UnsatisfiedLinkError unloaded) { return false; }
        }
    }
}
