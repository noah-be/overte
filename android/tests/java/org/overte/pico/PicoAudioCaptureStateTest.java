// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

public final class PicoAudioCaptureStateTest {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Object first = new Object();
        Object second = new Object();

        require(PicoAudioCaptureState.shouldDeliver(true, first, first, 1920),
            "the current running recorder must deliver positive reads");
        require(!PicoAudioCaptureState.shouldDeliver(false, first, first, 1920),
            "a stopped recorder must discard a final read");
        require(!PicoAudioCaptureState.shouldDeliver(true, second, first, 1920),
            "a replaced recorder must not enter the new source FIFO");
        require(!PicoAudioCaptureState.shouldDeliver(true, first, first, 0),
            "an empty read must not be delivered");
        require(!PicoAudioCaptureState.shouldDeliver(true, first, first, -3),
            "a failed read must not be delivered");
    }
}
