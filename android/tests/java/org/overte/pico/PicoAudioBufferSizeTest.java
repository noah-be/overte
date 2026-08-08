// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

public final class PicoAudioBufferSizeTest {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        require(PicoAudioBufferSize.callbackBytes(48_000, 1, 480) == 1920,
            "callback must retain the existing 20 ms mono minimum");
        require(PicoAudioBufferSize.callbackBytes(48_000, 2, 480) == 3840,
            "callback must retain the existing 20 ms stereo minimum");
        require(PicoAudioBufferSize.callbackBytes(48_000, 1, 1920) == 3840,
            "larger native callbacks must remain authoritative");
        require(PicoAudioBufferSize.recorderBytes(1024, 1920) == 3840,
            "recorder must buffer at least two callbacks");
        require(PicoAudioBufferSize.recorderBytes(8192, 1920) == 8192,
            "Android minimum must remain authoritative");

        require(PicoAudioBufferSize.callbackBytes(0, 1, 480) == -1,
            "zero sample rate must fail");
        require(PicoAudioBufferSize.callbackBytes(48_000, 0, 480) == -1,
            "zero channels must fail");
        require(PicoAudioBufferSize.callbackBytes(48_000, 3, 480) == -1,
            "unsupported channel count must fail");
        require(PicoAudioBufferSize.callbackBytes(48_000, 1, 0) == -1,
            "zero callback frames must fail");
        require(PicoAudioBufferSize.callbackBytes(
                Integer.MAX_VALUE, 2, Integer.MAX_VALUE) == -1,
            "callback multiplication overflow must fail");
        require(PicoAudioBufferSize.recorderBytes(1, Integer.MAX_VALUE) == -1,
            "double-callback recorder overflow must fail");
    }
}
