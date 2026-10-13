// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.qtproject.qt5.android;
/** JVM Qt Activity identity boundary. */
public final class QtNative { public static android.app.Activity owner;
    public static android.app.Activity activity() { return owner; }
}
