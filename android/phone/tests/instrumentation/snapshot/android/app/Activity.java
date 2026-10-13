// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package android.app;
/** JVM Activity boundary; no Android OS behavior is claimed. */
public class Activity { public boolean focused, finishing;
    public boolean hasWindowFocus() { return focused; }
    public boolean isFinishing() { return finishing; }
}
