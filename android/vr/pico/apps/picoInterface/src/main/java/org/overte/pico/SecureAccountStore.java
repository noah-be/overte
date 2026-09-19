// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.attribute.BasicFileAttributes;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

/** Android-only storage primitive. Account migration is owned by the PX-15 binding.
 * All callers in this process share one lock; only ciphertext reaches disk.
 * Missing, invalidated or unavailable keys never select a plaintext fallback.
 */
public final class SecureAccountStore {
    static final class UnavailableException extends GeneralSecurityException {
        UnavailableException() { super("protected store unavailable"); }
    }
    private static final Object LOCK = new Object();
    private static final String PROVIDER = "AndroidKeyStore";
    private final File directory;

    public SecureAccountStore(Context context) {
        directory = new File(context.getNoBackupFilesDir(), "pico-protected-records");
    }

    public byte[] read(String slot) throws IOException, GeneralSecurityException {
        synchronized (LOCK) {
            AtomicFile file = file(slot);
            if (!exists(file)) {
                return null;
            }
            KeyStore keys = keys();
            if (!keys.containsAlias(alias(slot))) {
                throw new ProtectedRecordCodec.InvalidRecordException();
            }
            byte[] envelope;
            try (FileInputStream input = file.openRead();
                    ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    if (output.size() + count > ProtectedRecordCodec.MAX_ENVELOPE) {
                        throw new ProtectedRecordCodec.InvalidRecordException();
                    }
                    output.write(buffer, 0, count);
                }
                envelope = output.toByteArray();
            }
            return ProtectedRecordCodec.decrypt(key(keys, slot, false), slot, envelope);
        }
    }

    public void write(String slot, byte[] value) throws IOException, GeneralSecurityException {
        synchronized (LOCK) {
            AtomicFile file = file(slot);
            if (!directory.isDirectory() && !directory.mkdirs()) {
                throw new IOException("protected record directory unavailable");
            }
            byte[] encrypted = ProtectedRecordCodec.encrypt(
                key(keys(), slot, !exists(file)), slot, value);
            FileOutputStream stream = file.startWrite();
            try {
                stream.write(encrypted);
                file.finishWrite(stream);
            } catch (IOException | RuntimeException error) {
                file.failWrite(stream);
                throw error;
            }
            // Confirm authenticated readback before the caller may migrate/delete legacy data.
            byte[] readback = read(slot);
            try {
                if (!java.security.MessageDigest.isEqual(value, readback)) {
                    throw new IOException("protected record readback failed");
                }
            } finally {
                if (readback != null) java.util.Arrays.fill(readback, (byte) 0);
            }
        }
    }

    public void remove(String slot) throws IOException, GeneralSecurityException {
        synchronized (LOCK) {
            AtomicFile file = file(slot);
            // Destroy the slot's key as well, so an old ciphertext cannot be replayed.
            KeyStore keys = keys();
            keys.deleteEntry(alias(slot));
            file.delete();
            if (exists(file) || keys.containsAlias(alias(slot))) {
                throw new IOException("protected record removal failed");
            }
        }
    }

    private AtomicFile file(String slot) {
        if (slot == null || !slot.matches("[a-z][a-z0-9-]{0,63}")) {
            throw new IllegalArgumentException("invalid protected record slot");
        }
        return new AtomicFile(new File(directory, slot + ".bin"));
    }

    private static boolean exists(AtomicFile file) throws IOException, GeneralSecurityException {
        // AtomicFile.exists() is not in the minimum API 26 SDK. Include recovery
        // files so an interrupted write with a lost key never creates a new key.
        boolean base = recordPathExists(file.getBaseFile());
        boolean backup = recordPathExists(new File(file.getBaseFile().getPath() + ".bak"));
        boolean pending = recordPathExists(new File(file.getBaseFile().getPath() + ".new"));
        return base || backup || pending;
    }

    private static boolean recordPathExists(File file) throws IOException, GeneralSecurityException {
        try {
            BasicFileAttributes attributes = Files.readAttributes(file.toPath(),
                BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attributes.isRegularFile()) throw new ProtectedRecordCodec.InvalidRecordException();
            return true;
        } catch (NoSuchFileException absent) {
            return false;
        }
        // Inaccessible paths must throw; File.exists() would conflate them with absence.
    }

    private static String alias(String slot) {
        return "org.overte.pico.protected.v1." + slot;
    }

    private static KeyStore keys() throws GeneralSecurityException, IOException {
        try {
            KeyStore keys = KeyStore.getInstance(PROVIDER);
            keys.load(null);
            return keys;
        } catch (GeneralSecurityException | IOException error) {
            throw new UnavailableException();
        }
    }

    private static SecretKey key(KeyStore keys, String slot, boolean mayCreate)
            throws GeneralSecurityException {
        String alias = alias(slot);
        if (!keys.containsAlias(alias)) {
            if (!mayCreate) {
                throw new ProtectedRecordCodec.InvalidRecordException();
            }
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER);
            generator.init(new KeyGenParameterSpec.Builder(alias,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(256)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build());
            return generator.generateKey();
        }
        KeyStore.Entry entry = keys.getEntry(alias, null);
        if (!(entry instanceof KeyStore.SecretKeyEntry)) {
            throw new ProtectedRecordCodec.InvalidRecordException();
        }
        return ((KeyStore.SecretKeyEntry) entry).getSecretKey();
    }
}
