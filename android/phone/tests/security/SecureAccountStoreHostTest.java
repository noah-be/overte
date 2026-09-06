package org.overte.phone;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

/** Real JCA encryption with a test-only key provider; no Android evidence. */
public final class SecureAccountStoreHostTest {
    private static int checks;
    private static final class TestKeys implements SecureAccountStore.Keys {
        SecretKey key;
        boolean unavailable;
        boolean deleteFails;
        public SecretKey find() throws GeneralSecurityException {
            if (unavailable) {
                throw new GeneralSecurityException("private provider diagnostic");
            }
            return key;
        }
        public SecretKey create() throws GeneralSecurityException {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(256);
            key = generator.generateKey();
            return key;
        }
        public void delete() throws GeneralSecurityException {
            if (deleteFails) {
                throw new GeneralSecurityException("private provider diagnostic");
            }
            key = null;
        }
    }
    private interface Action { void run() throws Exception; }
    private static void require(boolean condition) {
        checks++;
        if (!condition) {
            throw new AssertionError("protected storage assertion " + checks);
        }
    }
    private static void failure(SecureAccountStore.Failure expected, Action action)
            throws Exception {
        try {
            action.run();
            throw new AssertionError("expected storage failure");
        } catch (SecureAccountStore.StoreException error) {
            require(error.failure == expected);
            require(error.getMessage().equals(expected.name()));
            require(error.getCause() == null);
        }
    }
    public static void main(String[] args) throws Exception {
        File root = new File(args[0]);
        TestKeys keys = new TestKeys();
        File directory = new File(root, "record");
        File ciphertext = new File(directory, "account.gcm");
        SecureAccountStore store = new SecureAccountStore(directory, keys);
        require(store.read() == null);
        require(keys.key == null);
        byte[] value = "synthetic secret credential".getBytes(StandardCharsets.UTF_8);
        store.write(value);
        require(Arrays.equals(value, store.read()));
        byte[] first = Files.readAllBytes(ciphertext.toPath());
        require(!new String(first, StandardCharsets.ISO_8859_1).contains("synthetic secret"));
        store.write(value);
        byte[] second = Files.readAllBytes(ciphertext.toPath());
        require(!Arrays.equals(first, second));
        require(Arrays.equals(value, store.read()));
        second[second.length - 1] ^= 1;
        Files.write(ciphertext.toPath(), second);
        failure(SecureAccountStore.Failure.CORRUPT, store::read);
        store.write(value);
        keys.key = null;
        failure(SecureAccountStore.Failure.MISSING_KEY, store::read);
        failure(SecureAccountStore.Failure.MISSING_KEY, () -> store.write(value));
        require(keys.key == null);
        store.clear();
        require(store.read() == null);
        store.write(value);
        keys.unavailable = true;
        failure(SecureAccountStore.Failure.KEY_UNAVAILABLE, store::read);
        failure(SecureAccountStore.Failure.KEY_UNAVAILABLE, () -> store.write(value));
        keys.unavailable = false;
        keys.deleteFails = true;
        failure(SecureAccountStore.Failure.DELETE, store::clear);
        require(!ciphertext.exists());
        keys.deleteFails = false;
        store.clear();
        require(keys.key == null);
        store.clear();
        failure(SecureAccountStore.Failure.INPUT, () -> store.write(null));
        failure(SecureAccountStore.Failure.INPUT, () -> store.write(new byte[0]));
        failure(SecureAccountStore.Failure.INPUT,
                () -> store.write(new byte[SecureAccountStore.MAX_RECORD_BYTES + 1]));
        File parentFile = new File(root, "not-a-directory");
        Files.write(parentFile.toPath(), new byte[] { 1 });
        SecureAccountStore unwritable = new SecureAccountStore(parentFile, keys);
        failure(SecureAccountStore.Failure.WRITE, () -> unwritable.write(value));
        File target = new File(root, "symlink-target");
        Files.write(target.toPath(), new byte[] { 7 });
        Files.createSymbolicLink(ciphertext.toPath(), target.toPath());
        failure(SecureAccountStore.Failure.READ, store::read);
        failure(SecureAccountStore.Failure.WRITE, () -> store.write(value));
        failure(SecureAccountStore.Failure.DELETE, store::clear);
        require(Files.readAllBytes(target.toPath())[0] == 7);
        Files.delete(ciphertext.toPath());
        Files.createDirectory(ciphertext.toPath());
        failure(SecureAccountStore.Failure.READ, store::read);
        Files.delete(ciphertext.toPath());
        store.write(value);
        Files.write(ciphertext.toPath(), new byte[] { 1 });
        failure(SecureAccountStore.Failure.CORRUPT, store::read);
        store.clear();
        require(keys.key == null);
        System.out.println("SecureAccountStore host: " + checks + " assertions PASS");
    }
}
