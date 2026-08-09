package io.highfidelity.hifiinterface;

import java.security.SecureRandom;

public final class LegacyOAuthStatePolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class FixedRandom extends SecureRandom {
        private final int mode;
        private int calls;
        private int requestedBytes;

        FixedRandom(int mode) {
            this.mode = mode;
        }

        @Override
        public void nextBytes(byte[] bytes) {
            calls++;
            requestedBytes = bytes.length;
            for (int index = 0; index < bytes.length; index++) {
                bytes[index] = (byte) (mode < 0 ? index : mode);
            }
        }
    }

    public static void main(String[] args) {
        FixedRandom sequence = new FixedRandom(-1);
        String state = LegacyOAuthStatePolicy.generate(sequence);
        check(state.equals("steam-000102030405060708090a0b0c0d0e0f"
                        + "101112131415161718191a1b1c1d1e1f"),
                "all 256 random bits must be encoded in stable order");
        check(sequence.calls == 1 && sequence.requestedBytes == 32,
                "the entropy source must fill one 32-byte buffer exactly once");
        check(state.matches("steam-[0-9a-f]{64}"),
                "OAuth state must be URL-safe lowercase hexadecimal");
        check(!state.substring(6).matches(".*[+/=\\s-].*"),
                "encoded entropy must not contain separators or whitespace");

        String zeros = LegacyOAuthStatePolicy.generate(new FixedRandom(0));
        String ones = LegacyOAuthStatePolicy.generate(new FixedRandom(0xff));
        check(zeros.equals("steam-" + repeat("00", 32)),
                "leading zero bytes must be preserved");
        check(ones.equals("steam-" + repeat("ff", 32)),
                "bytes must be encoded unsigned");
        try {
            LegacyOAuthStatePolicy.generate(null);
            throw new AssertionError("null entropy sources must fail");
        } catch (NullPointerException expected) {
            assertions++;
        }
        System.out.println("LegacyOAuthStatePolicyStandaloneTest: " + assertions
                + " assertions passed");
    }

    private static String repeat(String value, int count) {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < count; index++) {
            result.append(value);
        }
        return result.toString();
    }
}
