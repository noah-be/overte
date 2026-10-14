// Test-only Android provider boundary; actual module API is compiled separately.
package org.overte.snapshot;
import android.content.Intent;
public final class SnapshotAdapter {
    public static void initialize(SnapshotHost owner) {}
    public static void foreground(SnapshotHost owner) {}
    public static void detach(SnapshotHost owner) {}
    public static boolean activityResult(SnapshotHost owner,int code,int result,Intent data) {return false;}
}
