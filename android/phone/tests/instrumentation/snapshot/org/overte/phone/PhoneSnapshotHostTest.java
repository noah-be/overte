// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.phone;
import org.overte.snapshot.SnapshotAdapter;
import org.qtproject.qt5.android.QtNative;
/** Executes production Host lifecycle with explicit OS/Qt identity fixtures. */
public final class PhoneSnapshotHostTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) {
        PhoneInterfaceActivity activity=new PhoneInterfaceActivity(); QtNative.owner=activity;
        PhoneSnapshotHost host=new PhoneSnapshotHost(activity);
        check(host.activity()==activity && !host.isForeground());
        host.foreground(true); host.windowFocus(); check(SnapshotAdapter.foregrounded==0);
        check(!host.activityResult(77, 0, null)); host.initialize(); host.initialize();
        check(SnapshotAdapter.initialized==1); activity.focused=true; host.windowFocus();
        check(host.isForeground() && SnapshotAdapter.foregrounded==1);
        check(host.activityResult(77, 0, null) && !host.activityResult(78, 0, null));
        host.foreground(false); host.windowFocus(); check(!host.isForeground() && SnapshotAdapter.foregrounded==1);
        host.foreground(true); check(SnapshotAdapter.foregrounded==2);
        activity.focused=false; host.windowFocus(); check(SnapshotAdapter.foregrounded==2);
        activity.focused=true; QtNative.owner=new PhoneInterfaceActivity(); host.windowFocus();
        check(!host.isForeground() && SnapshotAdapter.foregrounded==2);
        QtNative.owner=activity; activity.finishing=true; host.windowFocus();
        check(!host.isForeground() && SnapshotAdapter.foregrounded==2);
        activity.finishing=false; host.windowFocus(); check(SnapshotAdapter.foregrounded==3);
        host.detach(); check(SnapshotAdapter.detached==1 && !host.isForeground());
        check(!host.activityResult(77, 0, null)); host.windowFocus(); host.detach();
        check(SnapshotAdapter.detached==1 && SnapshotAdapter.foregrounded==3);
        System.out.println("PASS: actual PhoneSnapshotHost readiness, Activity identity, focus/resume, result routing and detach; OS endpoint is a fixture");
    }
}
