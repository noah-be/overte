// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

/** Overflow-safe PCM16 buffer sizing independent of Android audio classes. */
final class PicoAudioBufferSize {
    private static final int BYTES_PER_SAMPLE = Short.BYTES;

    private PicoAudioBufferSize() {
    }

    static int callbackBytes(int sampleRate, int channelCount, int framesPerBuffer) {
        if (sampleRate <= 0 || framesPerBuffer <= 0
                || (channelCount != 1 && channelCount != 2)) {
            return -1;
        }
        long bytesPerFrame = (long) channelCount * BYTES_PER_SAMPLE;
        long requested = (long) framesPerBuffer * bytesPerFrame;
        long twentyMilliseconds = (long) sampleRate * bytesPerFrame / 50L;
        long result = Math.max(requested, twentyMilliseconds);
        return result > Integer.MAX_VALUE ? -1 : (int) result;
    }

    static int recorderBytes(int minimumBytes, int callbackBytes) {
        if (minimumBytes <= 0 || callbackBytes <= 0) {
            return -1;
        }
        long result = Math.max((long) minimumBytes, (long) callbackBytes * 2L);
        return result > Integer.MAX_VALUE ? -1 : (int) result;
    }
}
