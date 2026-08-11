// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

/** Thread-safe lifecycle ownership for callbacks entering from native code. */
final class PicoActivityInstancePolicy<T> {
    private T current;

    synchronized void register(T instance) {
        current = instance;
    }

    synchronized void clear(T instance) {
        if (current == instance) {
            current = null;
        }
    }

    synchronized T current() {
        return current;
    }
}
