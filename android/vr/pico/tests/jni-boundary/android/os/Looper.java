// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package android.os;
/** Host-only OS boundary. No Android Looper or WebView is executed. */
public final class Looper {
    private static final Looper MAIN = new Looper();
    public static Looper getMainLooper() { return MAIN; }
    public static Looper myLooper() { return MAIN; }
}
