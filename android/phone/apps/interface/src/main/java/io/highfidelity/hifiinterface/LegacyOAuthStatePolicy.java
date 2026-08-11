package io.highfidelity.hifiinterface;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Objects;

/** Cryptographic OAuth callback correlation state for the legacy login flow. */
public final class LegacyOAuthStatePolicy {
    private static final int RANDOM_BYTES = 32;
    private static final char[] HEX = "0123456789abcdef".toCharArray();

    private LegacyOAuthStatePolicy() {
    }

    public static String generate(SecureRandom random) {
        Objects.requireNonNull(random, "random");
        byte[] bytes = new byte[RANDOM_BYTES];
        random.nextBytes(bytes);
        StringBuilder state = new StringBuilder("steam-");
        for (byte value : bytes) {
            int unsigned = value & 0xff;
            state.append(HEX[unsigned >>> 4]);
            state.append(HEX[unsigned & 0x0f]);
        }
        return state.toString();
    }

    public static boolean isValidCallback(
            String expectedState, String returnedState, String authorizationCode) {
        if (!hasText(expectedState) || !hasText(returnedState)
                || !hasText(authorizationCode)) {
            return false;
        }
        return MessageDigest.isEqual(
                expectedState.getBytes(StandardCharsets.UTF_8),
                returnedState.getBytes(StandardCharsets.UTF_8));
    }

    private static boolean hasText(String value) {
        return value != null && !value.trim().isEmpty();
    }
}
