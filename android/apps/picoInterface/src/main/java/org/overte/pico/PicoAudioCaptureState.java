// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

/** Device-independent delivery guard for AudioRecord lifecycle transitions. */
final class PicoAudioCaptureState {
    private PicoAudioCaptureState() {
    }

    static boolean shouldDeliver(
            boolean running, Object currentRecorder, Object activeRecorder, int bytesRead) {
        return bytesRead > 0 && running && currentRecorder == activeRecorder;
    }
}
