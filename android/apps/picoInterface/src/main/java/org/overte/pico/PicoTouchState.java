// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

/** Tracks the Android downTime shared by one WebView touch gesture. */
final class PicoTouchState {
    static final int ACTION_DOWN = 0;
    static final int ACTION_UP = 1;
    static final int ACTION_MOVE = 2;
    static final int ACTION_CANCEL = 3;

    private boolean active;
    private long downTime;

    long downTimeFor(int action, long eventTime) {
        if (action == ACTION_DOWN) {
            active = true;
            downTime = eventTime;
            return downTime;
        }

        final long result = active ? downTime : eventTime;
        if (action == ACTION_UP || action == ACTION_CANCEL) {
            active = false;
        }
        return result;
    }

    boolean isActive() {
        return active;
    }
}
