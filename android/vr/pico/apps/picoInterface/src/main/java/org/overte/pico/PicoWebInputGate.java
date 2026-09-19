package org.overte.pico;

import java.lang.ref.WeakReference;

/** Pico-local queued WebView input ownership, not a Shared lifecycle API. */
final class PicoWebInputGate {
    static final class Ticket {
        final WeakReference<Object> owner;
        final long generation;
        Ticket(WeakReference<Object> owner, long generation) {
            this.owner = owner;
            this.generation = generation;
        }
    }

    private WeakReference<Object> owner = new WeakReference<>(null);
    private long generation = 1;
    private boolean allowed;

    synchronized void update(Object nextOwner, boolean foreground) {
        if (owner.get() == nextOwner && allowed == foreground) return;
        if (generation < Long.MAX_VALUE) ++generation;
        owner = new WeakReference<>(nextOwner);
        allowed = foreground && nextOwner != null && generation < Long.MAX_VALUE;
    }

    synchronized Ticket capture() {
        return allowed && owner.get() != null ? new Ticket(owner, generation) : null;
    }

    synchronized boolean permits(Ticket ticket, Object currentOwner) {
        return ticket != null && allowed && currentOwner != null
            && generation == ticket.generation && owner.get() == currentOwner
            && ticket.owner.get() == currentOwner;
    }
}
