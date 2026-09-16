package org.overte.phone;

import java.io.File;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.security.GeneralSecurityException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

/** Test-only key provider; exercises production Java through real JNI. */
public final class SecureAccountStoreJniFixture {
    private static final class Keys implements SecureAccountStore.Keys {
        SecretKey key;
        boolean unavailable;
        boolean deleteFails;
        public SecretKey find() throws GeneralSecurityException {
            if (unavailable) { throw new GeneralSecurityException("synthetic private detail"); }
            return key;
        }
        public SecretKey create() throws GeneralSecurityException {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(256);
            return key = generator.generateKey();
        }
        public void delete() throws GeneralSecurityException {
            if (deleteFails) { throw new GeneralSecurityException("synthetic private detail"); }
            key = null;
        }
    }
    private static final Keys keys = new Keys();
    private static File record;
    public static void fault(int kind) throws Exception {
        keys.unavailable = kind == 1;
        keys.deleteFails = kind == 3;
        if (kind == 2) { keys.key = null; }
        if (kind == 4) { Files.write(record.toPath(), new byte[] { 1 }); }
        if (kind == 5) {
            Files.deleteIfExists(record.toPath());
            Files.createDirectory(record.toPath());
        }
        if (kind == 6) { Files.delete(record.toPath()); }
    }
    private static native int run();
    public static void main(String[] args) throws Exception {
        File directory = new File(args[0], "protected-account");
        record = new File(directory, "account.gcm");
        Field prepared = SecureAccountStore.class.getDeclaredField("prepared");
        prepared.setAccessible(true);
        prepared.set(null, new SecureAccountStore(directory, keys));
        // The production JNI_OnLoad registers against a test-only AccountManager
        // seam. Its store, transport and Shared migration coordinator are real.
        System.load(args[1]);
        System.out.println("Protected storage JNI: " + run() + " assertions PASS");
    }
}
