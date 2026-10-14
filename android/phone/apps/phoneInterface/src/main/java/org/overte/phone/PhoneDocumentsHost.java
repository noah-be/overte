// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.phone;

import android.app.Activity;
import android.content.Intent;
import org.overte.documents.DocumentAdapter;
import org.overte.documents.DocumentHost;
import org.qtproject.qt5.android.QtNative;

/** This immutable Activity receives only its own system document returns. */
final class PhoneDocumentsHost implements DocumentHost {
    private final PhoneInterfaceActivity activity;
    private boolean initialized, resumed;
    PhoneDocumentsHost(PhoneInterfaceActivity activity) { this.activity = activity; }
    void initialize() {
        if (initialized) return;
        DocumentAdapter.initialize(this); initialized = true;
    }
    void foreground(boolean value) { resumed = value; windowFocus(); }
    void windowFocus() { if (initialized && isForeground()) DocumentAdapter.foreground(this); }
    void detach() {
        resumed = false;
        if (initialized) DocumentAdapter.detach(this);
        initialized = false;
    }
    boolean activityResult(int code, int result, Intent data) {
        return initialized && DocumentAdapter.activityResult(this, code, result, data);
    }
    @Override public Activity activity() { return activity; }
    @Override public boolean isForeground() {
        return resumed && QtNative.activity() == activity && activity.hasWindowFocus() && !activity.isFinishing();
    }
}
