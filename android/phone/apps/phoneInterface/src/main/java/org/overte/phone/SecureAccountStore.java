package org.overte.phone;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.StandardCopyOption;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.util.Arrays;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Phone-native storage of one opaque serialized account record.
 *
 * AndroidKeyStore owns the non-exportable key. Only authenticated ciphertext
 * enters noBackupFilesDir. Operations are synchronous under the serialized
 * Shared account caller; its scheduling and latency require native validation.
 * Shared credential serialization/migration is deliberately external.
 */
public final class SecureAccountStore {
    private static SecureAccountStore prepared;

    /** Prepares trusted app paths, without key/account reads, before Qt loads. */
    static synchronized void prepare(Context context) {
        if (prepared == null) {
            try {
                prepared = new SecureAccountStore(context);
            } catch (RuntimeException unavailable) {
                RedactingDiagnostics.storageFailure(Failure.KEY_UNAVAILABLE);
                // JNI installs an unavailable adapter. No raw native details
                // or fallback storage escape a failed context preparation.
            }
        }
    }

    // Called by libphoneInterface JNI_OnLoad, before the native account caller.
    private static synchronized SecureAccountStore preparedStore() {
        return prepared;
    }
    private static final Object LOCK = new Object();
    private static final String ALIAS = "org.overte.phone.accounts.aes.v1";
    private static final byte[] AAD = {
        'O', 'V', 'E', 'R', 'T', 'E', '-', 'P', 'H', 'O', 'N', 'E', '-', '1'
    };
    private static final int MAGIC = 0x4f565031;
    private static final int IV_BYTES = 12;
    private static final int HEADER_BYTES = 4 + IV_BYTES;
    private static final int TAG_BYTES = 16;
    static final int MAX_RECORD_BYTES = 1024 * 1024;

    // Native failure distinctions; a published Shared adapter maps these to
    // the common taxonomy. No exception carries paths, ciphertext or tokens.
    public enum Failure { KEY_UNAVAILABLE, MISSING_KEY, READ, WRITE, CORRUPT, DELETE, INPUT }

    public static final class StoreException extends Exception {
        public final Failure failure;

        StoreException(Failure failure) {
            super(failure.name());
            this.failure = failure;
            RedactingDiagnostics.storageFailure(failure);
        }

        /** Phone JNI transport code; maps explicitly to PX-15 v001 outcomes. */
        public int nativeFailure() {
            switch (failure) {
                case KEY_UNAVAILABLE: return 1;
                case MISSING_KEY:
                case CORRUPT:
                case INPUT: return 2;
                default: return 3;
            }
        }
    }

    interface Keys {
        SecretKey find() throws GeneralSecurityException, IOException;
        SecretKey create() throws GeneralSecurityException, IOException;
        void delete() throws GeneralSecurityException, IOException;
    }

    private final File directory;
    private final File record;
    private final Keys keys;

    public SecureAccountStore(Context context) {
        this(privateDirectory(context), new AndroidKeys());
    }

    private static File privateDirectory(Context context) {
        try {
            // Normalize only the framework-owned root. A legitimate platform
            // data-directory alias must not look like a replaced account dir.
            // Do not canonicalize our child: checkPaths must reject its links.
            File root = context.getApplicationContext().getNoBackupFilesDir();
            if (root == null) { throw new IOException(); }
            return new File(root.getCanonicalFile(), "protected-account");
        } catch (IOException error) {
            throw new IllegalStateException("protected storage unavailable");
        }
    }

    // Test seam supplies keys only; production always selects AndroidKeyStore.
    SecureAccountStore(File directory, Keys keys) {
        this.directory = directory;
        this.record = new File(directory, "account.gcm");
        this.keys = keys;
    }

    /** Null means no record; unavailable/corrupt storage never looks empty. */
    public byte[] read() throws StoreException {
        synchronized (LOCK) {
            try {
                checkPaths();
                if (!Files.exists(record.toPath(), LinkOption.NOFOLLOW_LINKS)) {
                    return null;
                }
                long size = Files.size(record.toPath());
                if (size <= HEADER_BYTES + TAG_BYTES
                        || size > MAX_RECORD_BYTES + HEADER_BYTES + TAG_BYTES) {
                    throw new StoreException(Failure.CORRUPT);
                }
                byte[] envelope = new byte[(int) size];
                try (FileInputStream stream = new FileInputStream(record)) {
                    int offset = 0;
                    while (offset < envelope.length) {
                        int count = stream.read(envelope, offset, envelope.length - offset);
                        if (count < 0) {
                            throw new StoreException(Failure.CORRUPT);
                        }
                        offset += count;
                    }
                    if (stream.read() != -1) {
                        throw new StoreException(Failure.CORRUPT);
                    }
                }
                SecretKey key = findKey();
                if (key == null) {
                    throw new StoreException(Failure.MISSING_KEY);
                }
                return decrypt(key, envelope);
            } catch (IOException | SecurityException error) {
                throw new StoreException(Failure.READ);
            }
        }
    }

    /** Replaces the entire opaque record atomically, with no plaintext fallback. */
    public void write(byte[] value) throws StoreException {
        if (value == null || value.length == 0 || value.length > MAX_RECORD_BYTES) {
            throw new StoreException(Failure.INPUT);
        }
        byte[] secret = value.clone();
        synchronized (LOCK) {
            File temporary = null;
            try {
                checkPaths();
                SecretKey key = findKey();
                if (key == null) {
                    // An old record without its key needs explicit recovery,
                    // not a silent key replacement that hides credential loss.
                    if (record.exists()) {
                        throw new StoreException(Failure.MISSING_KEY);
                    }
                    try {
                        key = keys.create();
                    } catch (GeneralSecurityException | IOException | RuntimeException error) {
                        throw new StoreException(Failure.KEY_UNAVAILABLE);
                    }
                }
                byte[] envelope = encrypt(key, secret);
                if (!directory.isDirectory() && !directory.mkdirs()) {
                    throw new IOException();
                }
                if (!directory.setReadable(false, false)
                        || !directory.setWritable(false, false)
                        || !directory.setExecutable(false, false)
                        || !directory.setReadable(true, true)
                        || !directory.setWritable(true, true)
                        || !directory.setExecutable(true, true)) {
                    throw new IOException();
                }
                temporary = File.createTempFile("account-", ".tmp", directory);
                if (!temporary.setReadable(false, false)
                        || !temporary.setWritable(false, false)
                        || !temporary.setReadable(true, true)
                        || !temporary.setWritable(true, true)) {
                    throw new IOException();
                }
                try (FileOutputStream stream = new FileOutputStream(temporary)) {
                    stream.write(envelope);
                    stream.getFD().sync();
                }
                Files.move(temporary.toPath(), record.toPath(),
                        StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
                temporary = null;
            } catch (IOException | SecurityException error) {
                throw new StoreException(Failure.WRITE);
            } finally {
                Arrays.fill(secret, (byte) 0);
                if (temporary != null) {
                    // This contains ciphertext only. Never mask the first error.
                    temporary.delete();
                }
            }
        }
    }

    /**
     * Logout invalidates the key before deleting ciphertext. If either fails,
     * callers must still clear their in-memory credentials and report failure.
     */
    public void clear() throws StoreException {
        synchronized (LOCK) {
            boolean failed = false;
            try {
                keys.delete();
            } catch (GeneralSecurityException | IOException | RuntimeException error) {
                failed = true;
            }
            try {
                checkPaths();
                Files.deleteIfExists(record.toPath());
            } catch (IOException | SecurityException error) {
                failed = true;
            }
            if (failed) {
                throw new StoreException(Failure.DELETE);
            }
        }
    }

    private void checkPaths() throws IOException {
        if (!directory.getCanonicalFile().equals(directory.getAbsoluteFile())
                || Files.isSymbolicLink(record.toPath())
                || (record.exists() && !record.isFile())) {
            throw new IOException();
        }
    }

    private SecretKey findKey() throws StoreException {
        try {
            return keys.find();
        } catch (GeneralSecurityException | IOException | RuntimeException error) {
            throw new StoreException(Failure.KEY_UNAVAILABLE);
        }
    }

    private static byte[] encrypt(SecretKey key, byte[] value) throws StoreException {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key);
            byte[] iv = cipher.getIV();
            if (iv == null || iv.length != IV_BYTES) {
                throw new StoreException(Failure.WRITE);
            }
            cipher.updateAAD(AAD);
            byte[] encrypted = cipher.doFinal(value);
            return ByteBuffer.allocate(HEADER_BYTES + encrypted.length)
                    .putInt(MAGIC).put(iv).put(encrypted).array();
        } catch (GeneralSecurityException | RuntimeException error) {
            throw new StoreException(Failure.WRITE);
        }
    }

    private static byte[] decrypt(SecretKey key, byte[] envelope) throws StoreException {
        try {
            ByteBuffer buffer = ByteBuffer.wrap(envelope);
            if (buffer.getInt() != MAGIC) {
                throw new StoreException(Failure.CORRUPT);
            }
            byte[] iv = new byte[IV_BYTES];
            buffer.get(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
            cipher.updateAAD(AAD);
            return cipher.doFinal(envelope, HEADER_BYTES, envelope.length - HEADER_BYTES);
        } catch (GeneralSecurityException | RuntimeException error) {
            throw new StoreException(Failure.CORRUPT);
        }
    }

    private static final class AndroidKeys implements Keys {
        private KeyStore open() throws GeneralSecurityException, IOException {
            KeyStore store = KeyStore.getInstance("AndroidKeyStore");
            store.load(null);
            return store;
        }

        @Override
        public SecretKey find() throws GeneralSecurityException, IOException {
            KeyStore.Entry entry = open().getEntry(ALIAS, null);
            if (entry == null) {
                return null;
            }
            if (!(entry instanceof KeyStore.SecretKeyEntry)) {
                throw new GeneralSecurityException();
            }
            return ((KeyStore.SecretKeyEntry) entry).getSecretKey();
        }

        @Override
        public SecretKey create() throws GeneralSecurityException {
            KeyGenerator generator = KeyGenerator.getInstance(
                    KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setKeySize(256)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build());
            return generator.generateKey();
        }

        @Override
        public void delete() throws GeneralSecurityException, IOException {
            open().deleteEntry(ALIAS);
        }
    }
}
