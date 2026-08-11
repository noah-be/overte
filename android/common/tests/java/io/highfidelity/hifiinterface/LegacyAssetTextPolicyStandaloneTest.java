package io.highfidelity.hifiinterface;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class LegacyAssetTextPolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static InputStream shortReads(byte[] payload) {
        return new ByteArrayInputStream(payload) {
            @Override
            public int available() {
                return 0;
            }

            @Override
            public synchronized int read(byte[] target, int offset, int length) {
                return super.read(target, offset, Math.min(length, 1));
            }
        };
    }

    public static void main(String[] args) throws Exception {
        byte[] unicode = "Grüße 🚲".getBytes(StandardCharsets.UTF_8);
        check("Grüße 🚲".equals(LegacyAssetTextPolicy.readUtf8(shortReads(unicode), unicode.length)),
                "available() and partial reads must not truncate UTF-8 text");
        check("".equals(LegacyAssetTextPolicy.readUtf8(new ByteArrayInputStream(new byte[0]), 0)),
                "empty input must remain empty");
        check("abc".equals(LegacyAssetTextPolicy.readUtf8(
                new ByteArrayInputStream("abc".getBytes(StandardCharsets.UTF_8)), 3)),
                "input exactly at the limit must pass");

        try {
            LegacyAssetTextPolicy.readUtf8(
                    new ByteArrayInputStream("abcd".getBytes(StandardCharsets.UTF_8)), 3);
            throw new AssertionError("input above the limit must fail");
        } catch (IOException expected) {
            assertions++;
        }
        try {
            LegacyAssetTextPolicy.readUtf8(new ByteArrayInputStream(new byte[0]), -1);
            throw new AssertionError("negative limits must fail");
        } catch (IllegalArgumentException expected) {
            assertions++;
        }
        try {
            LegacyAssetTextPolicy.readUtf8(new InputStream() {
                @Override
                public int read() throws IOException {
                    throw new IOException("fixture");
                }
            }, 10);
            throw new AssertionError("read failures must propagate");
        } catch (IOException expected) {
            assertions++;
        }

        System.out.println("LegacyAssetTextPolicyStandaloneTest: " + assertions + " assertions passed");
    }
}
