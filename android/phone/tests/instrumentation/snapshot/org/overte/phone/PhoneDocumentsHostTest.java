// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.phone;
import org.overte.documents.DocumentAdapter;
import org.qtproject.qt5.android.QtNative;
/** Executes production Host lifecycle with explicit OS/Qt identity fixtures. */
public final class PhoneDocumentsHostTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) {
        PhoneInterfaceActivity activity=new PhoneInterfaceActivity(); QtNative.owner=activity;
        PhoneDocumentsHost host=new PhoneDocumentsHost(activity);
        check(host.activity()==activity && !host.isForeground());
        host.foreground(true); host.windowFocus(); check(DocumentAdapter.foregrounded==0);
        check(!host.activityResult(77, 0, null)); host.initialize(); host.initialize();
        check(DocumentAdapter.initialized==1); activity.focused=true; host.windowFocus();
        check(host.isForeground() && DocumentAdapter.foregrounded==1);
        check(host.activityResult(77, 0, null) && !host.activityResult(78, 0, null));
        host.foreground(false); host.windowFocus(); check(!host.isForeground() && DocumentAdapter.foregrounded==1);
        host.foreground(true); check(DocumentAdapter.foregrounded==2);
        activity.focused=false; host.windowFocus(); check(DocumentAdapter.foregrounded==2);
        activity.focused=true; QtNative.owner=new PhoneInterfaceActivity(); host.windowFocus();
        check(!host.isForeground() && DocumentAdapter.foregrounded==2);
        QtNative.owner=activity; activity.finishing=true; host.windowFocus();
        check(!host.isForeground() && DocumentAdapter.foregrounded==2);
        activity.finishing=false; host.windowFocus(); check(DocumentAdapter.foregrounded==3);
        host.detach(); check(DocumentAdapter.detached==1 && !host.isForeground());
        check(!host.activityResult(77, 0, null)); host.windowFocus(); host.detach();
        check(DocumentAdapter.detached==1 && DocumentAdapter.foregrounded==3);
        System.out.println("PASS: actual PhoneDocumentsHost readiness, Activity identity, focus/resume, result routing and detach; OS endpoint is a fixture");
    }
}
