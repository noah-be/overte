// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.graphics.Rect;
import android.net.Uri;
import android.webkit.MimeTypeMap;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import java.util.ArrayList;
import org.overte.security.SafeDiagnostics.Event;
import org.overte.web.EmbeddedWebHost;
import org.overte.web.EmbeddedWebView;
import org.overte.web.WebFilePickerState;
import org.qtproject.qt5.android.QtNative;

/** Headset surfaces use the shared Qt texture and the existing controller ray. */
final class PicoEmbeddedWebHost implements EmbeddedWebHost {
    private final PicoInterfaceActivity activity;
    private final WebFilePickerState<Uri[]> files = new WebFilePickerState<>();
    private boolean initialized;
    private boolean resumed;

    PicoEmbeddedWebHost(PicoInterfaceActivity activity) { this.activity = activity; }
    private static native void nativePrepareWeb(String cacheDirectory);
    void initialize() {
        if (initialized || !ownsActivity()) return;
        nativePrepareWeb(activity.getCacheDir().getAbsolutePath());
        EmbeddedWebView.initialize(this);
        initialized = true;
        foreground(resumed);
    }
    void foreground(boolean value) {
        resumed = value;
        // Denials must reach this immutable host even after Qt changes Activity.
        // The common host guard prevents an old host from suspending its successor.
        if (initialized) EmbeddedWebView.setForeground(this, isForeground());
        files.deliver(isInputFocused());
    }
    void windowFocus() {
        if (initialized) EmbeddedWebView.setInputFocused(this, isInputFocused());
        files.deliver(isInputFocused());
    }
    void detach() {
        resumed = false;
        files.cancel();
        if (initialized) EmbeddedWebView.detach(this);
        initialized = false;
    }
    @Override public Activity activity() { return activity; }
    @Override public boolean isForeground() {
        return initialized && resumed && ownsActivity()
            && !activity.isFinishing() && !activity.isDestroyed();
    }
    private boolean ownsActivity() {
        return PicoInterfaceActivity.getInstance() == activity && QtNative.activity() == activity;
    }
    private boolean isInputFocused() { return isForeground() && activity.hasWindowFocus(); }
    @Override public boolean placeTabletView(WebView view, Rect bounds) {
        // A headset tablet must remain a texture in the offscreen Qt scene.
        return false;
    }
    @Override public void removeTabletView(WebView view) { }
    @Override public void statusChanged(WebView view, int status) {
        // Native state publishes the visible status on the headset QML surface.
    }
    @Override public void diagnostic(int status) { RedactingDiagnostics.w(Event.REDACTED); }
    @Override public boolean openExternal(Uri url) {
        if (!isInputFocused() || url == null || url.getUserInfo() != null
                || !("https".equals(url.getScheme()) || "http".equals(url.getScheme()))) return false;
        try {
            Intent browser = new Intent(Intent.ACTION_VIEW, url).addCategory(Intent.CATEGORY_BROWSABLE);
            activity.startActivity(Intent.createChooser(browser, "Open in browser"));
            return true;
        } catch (ActivityNotFoundException | SecurityException unavailable) { return false; }
    }
    @Override public boolean chooseFiles(ValueCallback<Uri[]> result, WebChromeClient.FileChooserParams request) {
        if (!isInputFocused() || result == null || request == null
                || request.getMode() != WebChromeClient.FileChooserParams.MODE_OPEN
                && request.getMode() != WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) return false;
        int code = files.begin(result::onReceiveValue);
        if (code == 0) return false;
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
        picker.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, request.getMode() == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE);
        ArrayList<String> accepted = new ArrayList<>();
        String[] types = request.getAcceptTypes();
        for (String value : types == null ? new String[0] : types) {
            if (value == null) continue;
            String mime = value.startsWith(".")
                ? MimeTypeMap.getSingleton().getMimeTypeFromExtension(value.substring(1).toLowerCase(java.util.Locale.ROOT)) : value;
            if (mime != null && mime.matches("[A-Za-z0-9!#$&^_.+\\-]+/[A-Za-z0-9!#$&^_.+*\\-]+")
                    && accepted.size() < 16) accepted.add(mime);
        }
        if (!accepted.isEmpty()) picker.putExtra(Intent.EXTRA_MIME_TYPES, accepted.toArray(new String[0]));
        try { activity.startActivityForResult(picker, code); return true; }
        catch (ActivityNotFoundException | SecurityException unavailable) { files.cancel(); return false; }
    }
    boolean fileResult(int code, int result, Intent data) {
        if (!files.owns(code)) return false;
        ArrayList<Uri> values = new ArrayList<>();
        if (result == Activity.RESULT_OK && data != null) {
            ClipData clips = data.getClipData();
            if (clips != null) {
                for (int i = 0; i < Math.min(16, clips.getItemCount()); ++i) add(values, clips.getItemAt(i).getUri());
            } else { add(values, data.getData()); }
        }
        return files.receive(code, values.isEmpty() ? null : values.toArray(new Uri[0]), isInputFocused());
    }
    private static void add(ArrayList<Uri> selected, Uri uri) {
        if (uri != null && "content".equals(uri.getScheme()) && !selected.contains(uri)) selected.add(uri);
    }
}
