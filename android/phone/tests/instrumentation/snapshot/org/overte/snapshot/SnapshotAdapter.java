// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.snapshot;
/** OS export endpoint fixture; the production PhoneSnapshotHost remains real. */
public final class SnapshotAdapter {
    public static SnapshotHost current;
    public static int initialized, foregrounded, detached, returned;
    public static void initialize(SnapshotHost host) { current=host; ++initialized; }
    public static void foreground(SnapshotHost host) {
        if(current != host || !host.isForeground()) throw new AssertionError(); ++foregrounded;
    }
    public static void detach(SnapshotHost host) { if(current != host) throw new AssertionError(); current=null; ++detached; }
    public static boolean activityResult(SnapshotHost host, int code, int result, android.content.Intent data) {
        if(current != host) return false; ++returned; return code == 77;
    }
}
