// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

import android.app.Activity;
import android.graphics.Rect;
import android.net.Uri;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebView;

/** Product-owned Activity, screen transform and explicit OS permission boundary. */
public interface EmbeddedWebHost {
    Activity activity();
    /** Actual Activity foreground/ownership, independent of window input focus. */
    boolean isForeground();
    /** Rect is in the offscreen QML scene. The product applies its actual screen transform. */
    boolean placeTabletView(WebView view, Rect sceneBounds);
    /** Clip is the intersection of QML clip ancestors in the same scene coordinates. */
    default boolean placeTabletView(WebView view, Rect sceneBounds, Rect sceneClip) {
        return placeTabletView(view, sceneBounds);
    }
    void removeTabletView(WebView view);
    /** Must prompt through the OS; never return an arbitrary application file. */
    boolean chooseFiles(ValueCallback<Uri[]> result, WebChromeClient.FileChooserParams request);
    /** Explicit user action only; use an OS browser chooser for HTTP(S). */
    boolean openExternal(Uri url);
    /** Present nonzero closed statuses visibly; bridge-unavailable needs an update action. */
    void statusChanged(WebView view, int status);
    /** Closed status identifiers only; never pass URLs, messages, or exceptions to logs. */
    void diagnostic(int status);
}
