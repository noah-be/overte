package io.highfidelity.hifiinterface;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public final class LegacyCrashDumpPolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        check(!LegacyCrashDumpPolicy.isAcceptedLength(-1), "negative lengths must fail");
        check(LegacyCrashDumpPolicy.isAcceptedLength(0), "empty dumps are bounded");
        check(LegacyCrashDumpPolicy.isAcceptedLength(LegacyCrashDumpPolicy.MAX_DUMP_BYTES),
                "the exact maximum must pass");
        check(!LegacyCrashDumpPolicy.isAcceptedLength(LegacyCrashDumpPolicy.MAX_DUMP_BYTES + 1),
                "lengths above the maximum must fail");

        byte[] payload = new byte[50000];
        for (int i = 0; i < payload.length; i++) {
            payload[i] = (byte) (i * 31);
        }
        InputStream shortReads = new ByteArrayInputStream(payload) {
            @Override
            public synchronized int read(byte[] target, int offset, int length) {
                return super.read(target, offset, Math.min(7, length));
            }
        };
        ByteArrayOutputStream copied = new ByteArrayOutputStream();
        check(LegacyCrashDumpPolicy.copyBounded(shortReads, copied, payload.length) == payload.length,
                "copy must report every byte");
        check(Arrays.equals(payload, copied.toByteArray()), "partial reads must copy exactly");

        try {
            LegacyCrashDumpPolicy.copyBounded(
                    new ByteArrayInputStream(new byte[] { 1, 2 }), new ByteArrayOutputStream(), 1);
            throw new AssertionError("growing dumps must fail at the bound");
        } catch (IOException expected) {
            assertions++;
        }
        try {
            LegacyCrashDumpPolicy.copyBounded(
                    new ByteArrayInputStream(new byte[0]), new ByteArrayOutputStream(), -1);
            throw new AssertionError("negative copy bounds must fail");
        } catch (IllegalArgumentException expected) {
            assertions++;
        }

        System.out.println("LegacyCrashDumpPolicyStandaloneTest: " + assertions
                + " assertions passed");
    }
}
