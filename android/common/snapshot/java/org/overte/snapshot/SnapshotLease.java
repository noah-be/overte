// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.snapshot;

/** A completed OS operation cannot migrate to a new Activity, source or ticket. */
final class SnapshotLease {
    final long handle, ticket, generation;
    final Object owner;
    private boolean closed, cancelled;
    SnapshotLease(long handle, long ticket, long generation, Object owner) {
        this.handle = handle; this.ticket = ticket; this.generation = generation; this.owner = owner;
    }
    synchronized boolean accepts(long handle, long ticket, long generation, Object owner) {
        return !closed && this.handle == handle && this.ticket == ticket && this.generation == generation
            && this.owner == owner;
    }
    synchronized boolean close(long handle, long ticket, long generation, Object owner) {
        if (!accepts(handle, ticket, generation, owner)) return false;
        closed = true; return true;
    }
    synchronized boolean abort(long handle, long ticket, long generation, Object owner) {
        if (!close(handle, ticket, generation, owner)) return false;
        cancelled = true; return true;
    }
    synchronized boolean cancelled() { return cancelled; }
}
