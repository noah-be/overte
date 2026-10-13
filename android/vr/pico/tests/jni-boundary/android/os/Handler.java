// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package android.os;
/** Capture production commands at the OS scheduling boundary without running Android UI. */
public final class Handler {
    public static Runnable posted;
    public Handler(Looper looper) { }
    public boolean post(Runnable command) { posted = command; return true; }
    public boolean postDelayed(Runnable command, long delay) { return true; }
    public void removeCallbacks(Runnable command) { }
}
