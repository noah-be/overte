// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

/** Runs real production AES-GCM code with JVM test keys, never device key evidence. */
public final class ProtectedRecordCodecTest {
    private static int checks;
    interface Attempt { void run() throws Exception; }
    static void rejects(Attempt attempt) throws Exception {
        try {
            attempt.run();
        } catch (GeneralSecurityException expected) {
            checks++;
            return;
        }
        throw new AssertionError("expected authenticated rejection");
    }
    static void check(boolean result) {
        if (!result) throw new AssertionError("protected record contract failed");
        checks++;
    }
    public static void main(String[] ignored) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();
        byte[] value = "canary-credential-秘密-🙂".getBytes(StandardCharsets.UTF_8);
        byte[] record = ProtectedRecordCodec.encrypt(key, "account-map", value);
        check(Arrays.equals(value, ProtectedRecordCodec.decrypt(key, "account-map", record)));
        check(!new String(record, StandardCharsets.ISO_8859_1).contains("canary-credential"));
        check(!Arrays.equals(record, ProtectedRecordCodec.encrypt(key, "account-map", value)));
        rejects(() -> ProtectedRecordCodec.decrypt(generator.generateKey(), "account-map", record));
        rejects(() -> ProtectedRecordCodec.decrypt(key, "restart-arguments", record));
        for (int index = 0; index < record.length; index++) {
            byte[] corrupted = record.clone();
            corrupted[index] ^= 1;
            rejects(() -> ProtectedRecordCodec.decrypt(key, "account-map", corrupted));
        }
        for (int length = 0; length < record.length; length++) {
            final byte[] truncated = Arrays.copyOf(record, length);
            rejects(() -> ProtectedRecordCodec.decrypt(key, "account-map", truncated));
        }
        byte[] oversized = new byte[ProtectedRecordCodec.MAX_PLAINTEXT + 1];
        rejects(() -> ProtectedRecordCodec.encrypt(key, "account-map", oversized));
        rejects(() -> ProtectedRecordCodec.decrypt(key, "account-map",
            new byte[ProtectedRecordCodec.MAX_ENVELOPE + 1]));
        rejects(() -> ProtectedRecordCodec.encrypt(key, "account-map", null));
        check(ProtectedRecordCodec.decrypt(key, "account-map",
            ProtectedRecordCodec.encrypt(key, "account-map", new byte[0])).length == 0);
        System.out.println("PASS production protected-record codec: " + checks + " checks (host keys only)");
    }
}
