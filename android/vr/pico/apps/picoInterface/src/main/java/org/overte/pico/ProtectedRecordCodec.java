// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Versioned authenticated envelope used by the Android Keystore store. */
final class ProtectedRecordCodec {
    static final class InvalidRecordException extends GeneralSecurityException {
        InvalidRecordException() { super("invalid protected record"); }
    }
    static final int MAX_PLAINTEXT = 1024 * 1024;
    static final int HEADER_BYTES = 4 + 12;
    static final int MAX_ENVELOPE = HEADER_BYTES + MAX_PLAINTEXT + 16;
    private static final int MAGIC = 0x50435301;

    private ProtectedRecordCodec() { }

    static byte[] encrypt(SecretKey key, String purpose, byte[] plaintext)
            throws GeneralSecurityException {
        if (plaintext == null || plaintext.length > MAX_PLAINTEXT) {
            throw new InvalidRecordException();
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        // The Keystore provider generates the nonce; callers cannot reuse one.
        cipher.init(Cipher.ENCRYPT_MODE, key);
        byte[] iv = cipher.getIV();
        if (iv == null || iv.length != 12) {
            throw new GeneralSecurityException("invalid protected record nonce");
        }
        cipher.updateAAD(aad(purpose));
        byte[] ciphertext = cipher.doFinal(plaintext);
        return ByteBuffer.allocate(HEADER_BYTES + ciphertext.length)
            .putInt(MAGIC).put(iv).put(ciphertext).array();
    }

    static byte[] decrypt(SecretKey key, String purpose, byte[] envelope)
            throws GeneralSecurityException {
        if (envelope == null || envelope.length < HEADER_BYTES + 16
                || envelope.length > MAX_ENVELOPE
                || ByteBuffer.wrap(envelope).getInt() != MAGIC) {
            throw new InvalidRecordException();
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(128, Arrays.copyOfRange(envelope, 4, HEADER_BYTES)));
        cipher.updateAAD(aad(purpose));
        return cipher.doFinal(envelope, HEADER_BYTES, envelope.length - HEADER_BYTES);
    }

    private static byte[] aad(String purpose) {
        return ("org.overte.pico/protected-record/v1/" + purpose)
            .getBytes(StandardCharsets.UTF_8);
    }
}
