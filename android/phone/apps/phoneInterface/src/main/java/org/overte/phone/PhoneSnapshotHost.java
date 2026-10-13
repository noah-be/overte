// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.phone;

import android.app.Activity;
import android.content.Intent;
import org.overte.snapshot.SnapshotAdapter;
import org.overte.snapshot.SnapshotHost;
import org.qtproject.qt5.android.QtNative;

/** This immutable Activity receives only its own system export returns. */
final class PhoneSnapshotHost implements SnapshotHost {
    private final PhoneInterfaceActivity activity;
    private boolean initialized, resumed;
    PhoneSnapshotHost(PhoneInterfaceActivity activity) { this.activity = activity; }
    void initialize() {
        if (initialized) return;
        SnapshotAdapter.initialize(this); initialized = true;
    }
    void foreground(boolean value) { resumed = value; windowFocus(); }
    void windowFocus() { if (initialized && isForeground()) SnapshotAdapter.foreground(this); }
    void detach() {
        resumed = false;
        if (initialized) SnapshotAdapter.detach(this);
        initialized = false;
    }
    boolean activityResult(int code, int result, Intent data) {
        return initialized && SnapshotAdapter.activityResult(this, code, result, data);
    }
    @Override public Activity activity() { return activity; }
    @Override public boolean isForeground() {
        return resumed && QtNative.activity() == activity && activity.hasWindowFocus() && !activity.isFinishing();
    }
}
