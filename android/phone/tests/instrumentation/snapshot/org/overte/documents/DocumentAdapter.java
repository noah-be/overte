// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.documents;
/** OS document endpoint fixture; the production PhoneDocumentsHost remains real. */
public final class DocumentAdapter {
    public static DocumentHost current;
    public static int initialized, foregrounded, detached, returned;
    public static void initialize(DocumentHost host) { current=host; ++initialized; }
    public static void foreground(DocumentHost host) {
        if(current != host || !host.isForeground()) throw new AssertionError(); ++foregrounded;
    }
    public static void detach(DocumentHost host) { if(current != host) throw new AssertionError(); current=null; ++detached; }
    public static boolean activityResult(DocumentHost host, int code, int result, android.content.Intent data) {
        if(current != host) return false; ++returned; return code == 77;
    }
}
