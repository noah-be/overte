// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.qtproject.qt5.android;

/** Qt has no owner in Robolectric; native callbacks cannot become ready. */
public final class QtNative {
    public static android.app.Activity activity() { return null; }
    public static void setApplicationState(int state) {
        throw new AssertionError("Native Qt lifecycle requires an Android runtime");
    }
}
