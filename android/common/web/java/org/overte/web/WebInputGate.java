// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

import java.lang.ref.WeakReference;

/** A queued gesture never crosses Activity ownership or foreground generations. */
final class WebInputGate {
    static final class Ticket {
        final WeakReference<Object> owner;
        final long generation;
        Ticket(Object owner, long generation) {
            this.owner = new WeakReference<>(owner); this.generation = generation;
        }
    }
    private WeakReference<Object> owner = new WeakReference<>(null);
    private long generation;
    private boolean active;
    synchronized void update(Object next, boolean foreground) {
        if (owner.get() == next && active == foreground) return;
        if (generation < Long.MAX_VALUE) ++generation;
        owner = new WeakReference<>(next);
        active = foreground && next != null && generation < Long.MAX_VALUE;
    }
    synchronized Ticket capture() {
        Object current = owner.get();
        return active && current != null ? new Ticket(current, generation) : null;
    }
    synchronized boolean permits(Ticket ticket, Object current) {
        return ticket != null && active && current != null && owner.get() == current
            && ticket.owner.get() == current && ticket.generation == generation;
    }
}
