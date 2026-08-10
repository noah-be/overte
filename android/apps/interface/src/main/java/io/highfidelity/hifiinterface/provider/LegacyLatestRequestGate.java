package io.highfidelity.hifiinterface.provider;

import java.util.concurrent.atomic.AtomicLong;

/** Identifies the latest asynchronous request without framework dependencies. */
public final class LegacyLatestRequestGate {
    private final AtomicLong current = new AtomicLong();

    public long begin() {
        return current.updateAndGet(value -> value == Long.MAX_VALUE ? 1 : value + 1);
    }

    public boolean isCurrent(long ticket) {
        return ticket > 0 && current.get() == ticket;
    }
}
