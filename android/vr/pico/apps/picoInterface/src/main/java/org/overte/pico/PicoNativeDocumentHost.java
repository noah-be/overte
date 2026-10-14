// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.app.Activity;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import java.lang.ref.WeakReference;
import org.overte.documents.DocumentAdapter;
import org.overte.documents.DocumentHost;
import org.overte.snapshot.SnapshotAdapter;
import org.overte.snapshot.SnapshotHost;

/** One immutable Activity lease for native document import and Snapshot export. */
final class PicoNativeDocumentHost implements DocumentHost, SnapshotHost {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static WeakReference<PicoNativeDocumentHost> current = new WeakReference<>(null);
    private static boolean nativesBound;
    private final PicoInterfaceActivity activity;
    private volatile boolean resumed;
    private volatile boolean initialized;
    private volatile boolean detached;
    private boolean readyScheduled;

    private PicoNativeDocumentHost(PicoInterfaceActivity activity) { this.activity = activity; }

    static synchronized PicoNativeDocumentHost attach(PicoInterfaceActivity activity) {
        PicoNativeDocumentHost previous = current.get();
        if (previous != null) previous.detach();
        PicoNativeDocumentHost owner = new PicoNativeDocumentHost(activity);
        current = new WeakReference<>(owner);
        // A configuration-recreated Activity reuses the already loaded full
        // client and registered classes. Revoke the old lease, then initialize
        // the new immutable owner; application setup need not run a second time.
        if (nativesBound) nativeBindingsReady(activity);
        return owner;
    }

    // Called only after RegisterNatives in the full client. True admits an
    // Android-main-loop initialization; it is not an OS picker receipt.
    static synchronized boolean nativeBindingsReady(Object instance) {
        PicoNativeDocumentHost owner = current.get();
        if (owner == null || owner.activity != instance || !owner.ownsActivity()) return false;
        nativesBound = true;
        if (owner.readyScheduled || owner.initialized) return true;
        owner.readyScheduled = true;
        boolean posted = MAIN.post(() -> {
            if (!owner.ownsActivity()) return;
            DocumentAdapter.initialize(owner);
            SnapshotAdapter.initialize(owner);
            owner.initialized = true;
            owner.windowFocus();
        });
        if (!posted) owner.readyScheduled = false;
        return posted;
    }

    private boolean ownsActivity() {
        return !detached && PicoInterfaceActivity.getInstance() == activity && !activity.isFinishing();
    }
    void foreground(boolean value) { resumed = value; windowFocus(); }
    void windowFocus() {
        if (!initialized || !isForeground()) return;
        DocumentAdapter.foreground(this);
        SnapshotAdapter.foreground(this);
    }
    synchronized void detach() {
        if (detached) return;
        detached = true;
        resumed = false;
        if (initialized) {
            DocumentAdapter.detach(this);
            SnapshotAdapter.detach(this);
        }
        initialized = false;
    }
    boolean activityResult(int code, int result, Intent data) {
        if (!initialized || !ownsActivity()) return false;
        return DocumentAdapter.activityResult(this, code, result, data)
            || SnapshotAdapter.activityResult(this, code, result, data);
    }
    @Override public Activity activity() { return activity; }
    @Override public boolean isForeground() {
        return initialized && resumed && ownsActivity() && activity.hasWindowFocus();
    }
}
