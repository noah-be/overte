// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;
import java.lang.ref.WeakReference;

/** One OS picker return may survive suspension, but never a different document or owner. */
final class WebFileChoiceLease {
    private final WeakReference<Object> target, owner;
    private final long page;
    private final String source, document;
    private boolean consumed;
    WebFileChoiceLease(Object target, Object owner, long page, String source, String document) {
        this.target = new WeakReference<>(target); this.owner = new WeakReference<>(owner);
        this.page = page; this.source = source; this.document = document;
    }
    // 0: already completed; 1: cancel; 2: deliver the explicit OS selection.
    synchronized int consume(Object nextTarget, Object nextOwner, long nextPage, String nextSource,
            String nextDocument, boolean currentLease, boolean active, boolean visible,
            boolean foreground, boolean nativeAllowed) {
        if (consumed) return 0;
        consumed = true;
        return currentLease && active && visible && foreground && nativeAllowed
            && target.get() == nextTarget && owner.get() == nextOwner && page == nextPage
            && source != null && source.equals(nextSource) && document != null && document.equals(nextDocument) ? 2 : 1;
    }
}
