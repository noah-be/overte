// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

/** Per-document output fence. Native mute does not terminate JavaScript or AudioContext work. */
final class WebAudioLifecycle {
    interface Output {
        boolean mute(boolean value);
        void closeDocument();
    }
    static final class Ticket {
        final Object instance, owner;
        final long revision, page;
        final String document;
        Ticket(Object instance, Object owner, long revision, long page, String document) {
            this.instance = instance; this.owner = owner; this.revision = revision;
            this.page = page; this.document = document;
        }
    }
    private final Output output;
    private Ticket current;
    private boolean reliable, closed;
    WebAudioLifecycle(Output output) { this.output = output; reliable = mute(true); }
    private boolean mute(boolean value) {
        try { return output.mute(value); }
        catch (RuntimeException failure) { return false; }
    }
    Ticket document(Object instance, Object owner, long revision, long page, String url) {
        current = new Ticket(instance, owner, revision, page, url);
        return current;
    }
    boolean current(Ticket ticket, Object instance, Object owner, long revision, long page, String url) {
        return !closed && ticket != null && ticket == current && ticket.instance == instance && ticket.owner == owner
            && revision > 0 && page > 0 && ticket.revision == revision && ticket.page == page
            && ticket.document != null && ticket.document.equals(url);
    }
    boolean suspend() {
        current = null;
        if (closed) return false;
        if (reliable && mute(true)) return true;
        closed = true; output.closeDocument(); return false;
    }
    boolean audible(Ticket ticket, Object instance, Object owner, long revision, long page, String url,
            boolean visible, boolean foreground, boolean active, boolean committed) {
        if (!current(ticket, instance, owner, revision, page, url) || !visible || !foreground || !active || !committed) return false;
        // An older provider may use a visible document; it is destroyed on its first suspend.
        if (!reliable) return true;
        if (mute(false)) return true;
        reliable = false; suspend(); return false;
    }
    boolean closed() { return closed; }
}
