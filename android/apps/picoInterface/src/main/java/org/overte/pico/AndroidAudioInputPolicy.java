// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

/** Framework-free validation and sizing policy for {@link AndroidAudioInput}. */
public final class AndroidAudioInputPolicy {
    /** Hard allocation ceiling: normal 20 ms stereo/48 kHz callbacks use only 3,840 bytes. */
    public static final int MAX_CALLBACK_BYTES = 1024 * 1024;
    public static final int MAX_RECORDER_BYTES = MAX_CALLBACK_BYTES * 2;
    public enum Source { MIC, VOICE_COMMUNICATION, VOICE_RECOGNITION, CAMCORDER }
    public enum Channel { MONO, STEREO }

    public static final class BufferPlan {
        public final int callbackBytes;
        public final int recorderBytes;

        private BufferPlan(int callbackBytes, int recorderBytes) {
            this.callbackBytes = callbackBytes;
            this.recorderBytes = recorderBytes;
        }
    }

    private AndroidAudioInputPolicy() {
    }

    public static Source resolveSource(String requestedSource) {
        if (requestedSource == null || requestedSource.isEmpty() || requestedSource.equals("mic")) {
            return Source.MIC;
        }
        if (requestedSource.equals("voicecommunication")) {
            return Source.VOICE_COMMUNICATION;
        }
        if (requestedSource.equals("voicerecognition")) {
            return Source.VOICE_RECOGNITION;
        }
        if (requestedSource.equals("camcorder")) {
            return Source.CAMCORDER;
        }
        return null;
    }

    public static Channel resolveChannel(int channelCount) {
        if (channelCount == 1) {
            return Channel.MONO;
        }
        if (channelCount == 2) {
            return Channel.STEREO;
        }
        return null;
    }

    public static Integer calculateCallbackBytes(
            int sampleRate, int channelCount, int framesPerBuffer) {
        if (sampleRate <= 0 || resolveChannel(channelCount) == null || framesPerBuffer <= 0) {
            return null;
        }
        long frameBytes = (long) framesPerBuffer * channelCount * Short.BYTES;
        long twentyMillisecondBytes = (long) sampleRate * channelCount * Short.BYTES / 50L;
        long callbackBytes = Math.max(frameBytes, twentyMillisecondBytes);
        return callbackBytes > MAX_CALLBACK_BYTES ? null : (int) callbackBytes;
    }

    public static BufferPlan calculateBufferPlan(Integer callbackBytes, int minimumBytes) {
        if (callbackBytes == null || callbackBytes <= 0
                || callbackBytes > MAX_CALLBACK_BYTES
                || minimumBytes <= 0 || minimumBytes > MAX_RECORDER_BYTES) {
            return null;
        }
        long doubledCallback = (long) callbackBytes * 2L;
        long recorderBytes = Math.max((long) minimumBytes, doubledCallback);
        return new BufferPlan(callbackBytes, (int) recorderBytes);
    }

    /** Revalidates capture ownership after a blocking read and immediately before JNI delivery. */
    public static boolean shouldDeliverRead(int bytesRead, boolean running, boolean ownsRecorder) {
        return bytesRead > 0 && running && ownsRecorder;
    }
}
