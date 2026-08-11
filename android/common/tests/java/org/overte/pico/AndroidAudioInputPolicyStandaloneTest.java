package org.overte.pico;

/** Dependency-free regression/property tests for microphone selection and buffer sizing. */
public final class AndroidAudioInputPolicyStandaloneTest {
    private static int assertions;

    public static void main(String[] arguments) {
        sourceAllowlistIsExact();
        channelsAreExplicit();
        bufferExamplesPreserveExistingArithmetic();
        invalidAndOverflowingInputsFailClosed();
        staleReadsAreNeverDelivered();
        fixedSeedBufferOracle();
        System.out.println("AndroidAudioInputPolicyStandaloneTest: " + assertions + " assertions passed");
    }

    private static void sourceAllowlistIsExact() {
        same(AndroidAudioInputPolicy.Source.MIC, AndroidAudioInputPolicy.resolveSource(null));
        same(AndroidAudioInputPolicy.Source.MIC, AndroidAudioInputPolicy.resolveSource(""));
        same(AndroidAudioInputPolicy.Source.MIC, AndroidAudioInputPolicy.resolveSource("mic"));
        same(AndroidAudioInputPolicy.Source.VOICE_COMMUNICATION,
                AndroidAudioInputPolicy.resolveSource("voicecommunication"));
        same(AndroidAudioInputPolicy.Source.VOICE_RECOGNITION,
                AndroidAudioInputPolicy.resolveSource("voicerecognition"));
        same(AndroidAudioInputPolicy.Source.CAMCORDER,
                AndroidAudioInputPolicy.resolveSource("camcorder"));
        same(null, AndroidAudioInputPolicy.resolveSource("MIC"));
        same(null, AndroidAudioInputPolicy.resolveSource(" mic"));
        same(null, AndroidAudioInputPolicy.resolveSource("default"));
    }

    private static void channelsAreExplicit() {
        same(AndroidAudioInputPolicy.Channel.MONO, AndroidAudioInputPolicy.resolveChannel(1));
        same(AndroidAudioInputPolicy.Channel.STEREO, AndroidAudioInputPolicy.resolveChannel(2));
        same(null, AndroidAudioInputPolicy.resolveChannel(0));
        same(null, AndroidAudioInputPolicy.resolveChannel(3));
        same(null, AndroidAudioInputPolicy.resolveChannel(-1));
        same(null, AndroidAudioInputPolicy.resolveChannel(Integer.MIN_VALUE));
        same(null, AndroidAudioInputPolicy.resolveChannel(Integer.MAX_VALUE));
    }

    private static void bufferExamplesPreserveExistingArithmetic() {
        equal(1920, AndroidAudioInputPolicy.calculateCallbackBytes(48000, 1, 256));
        equal(3840, AndroidAudioInputPolicy.calculateCallbackBytes(48000, 2, 256));
        plan(1920, 4096, AndroidAudioInputPolicy.calculateBufferPlan(1920, 4096));
        plan(3840, 7680, AndroidAudioInputPolicy.calculateBufferPlan(3840, 1024));
    }

    private static void invalidAndOverflowingInputsFailClosed() {
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(0, 1, 1));
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(-1, 1, 1));
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(48000, 0, 1));
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(48000, 1, 0));
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(48000, 1, -1));
        equal(AndroidAudioInputPolicy.MAX_CALLBACK_BYTES,
                AndroidAudioInputPolicy.calculateCallbackBytes(
                        1, 1, AndroidAudioInputPolicy.MAX_CALLBACK_BYTES / Short.BYTES));
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(
                1, 1, AndroidAudioInputPolicy.MAX_CALLBACK_BYTES / Short.BYTES + 1));
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(
                1, 1, Integer.MAX_VALUE / 2));
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(
                1, 1, Integer.MAX_VALUE / 2 + 1));
        same(null, AndroidAudioInputPolicy.calculateCallbackBytes(
                Integer.MAX_VALUE, 2, Integer.MAX_VALUE));
        same(null, AndroidAudioInputPolicy.calculateBufferPlan(null, 1));
        same(null, AndroidAudioInputPolicy.calculateBufferPlan(0, 1));
        same(null, AndroidAudioInputPolicy.calculateBufferPlan(1, 0));
        plan(AndroidAudioInputPolicy.MAX_CALLBACK_BYTES,
                AndroidAudioInputPolicy.MAX_RECORDER_BYTES,
                AndroidAudioInputPolicy.calculateBufferPlan(
                        AndroidAudioInputPolicy.MAX_CALLBACK_BYTES, 1));
        same(null, AndroidAudioInputPolicy.calculateBufferPlan(
                AndroidAudioInputPolicy.MAX_CALLBACK_BYTES + 1, 1));
        same(null, AndroidAudioInputPolicy.calculateBufferPlan(
                1, AndroidAudioInputPolicy.MAX_RECORDER_BYTES + 1));
        same(null, AndroidAudioInputPolicy.calculateBufferPlan(Integer.MAX_VALUE, 1));
    }

    private static void fixedSeedBufferOracle() {
        long state = 0x415544494fL;
        for (int index = 0; index < 2048; ++index) {
            state = state * 6364136223846793005L + 1442695040888963407L;
            int sampleRate = 8000 + (int) ((state >>> 1) % 184001);
            int channels = 1 + (int) ((state >>> 17) & 1L);
            int frames = 1 + (int) ((state >>> 25) % 8192);
            long expected = Math.max((long) frames * channels * 2L,
                    (long) sampleRate * channels * 2L / 50L);
            equal((int) expected,
                    AndroidAudioInputPolicy.calculateCallbackBytes(sampleRate, channels, frames));
            int minimum = 1 + (int) ((state >>> 33) % 65536);
            long recorder = Math.max(minimum, expected * 2L);
            plan((int) expected, (int) recorder,
                    AndroidAudioInputPolicy.calculateBufferPlan((int) expected, minimum));
        }
    }

    private static void staleReadsAreNeverDelivered() {
        truth(true, AndroidAudioInputPolicy.shouldDeliverRead(1, true, true));
        truth(true, AndroidAudioInputPolicy.shouldDeliverRead(4096, true, true));
        truth(false, AndroidAudioInputPolicy.shouldDeliverRead(0, true, true));
        truth(false, AndroidAudioInputPolicy.shouldDeliverRead(-1, true, true));
        truth(false, AndroidAudioInputPolicy.shouldDeliverRead(1, false, true));
        truth(false, AndroidAudioInputPolicy.shouldDeliverRead(1, true, false));
        truth(false, AndroidAudioInputPolicy.shouldDeliverRead(1, false, false));
    }

    private static void plan(int callback, int recorder, AndroidAudioInputPolicy.BufferPlan plan) {
        ++assertions;
        if (plan == null || plan.callbackBytes != callback || plan.recorderBytes != recorder) {
            throw new AssertionError("unexpected buffer plan");
        }
    }

    private static void equal(int expected, Integer actual) {
        ++assertions;
        if (actual == null || actual != expected) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }

    private static void same(Object expected, Object actual) {
        ++assertions;
        if (expected != actual) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }

    private static void truth(boolean expected, boolean actual) {
        ++assertions;
        if (expected != actual) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }
}
