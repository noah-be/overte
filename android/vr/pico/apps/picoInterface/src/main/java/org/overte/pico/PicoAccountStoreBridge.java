// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.content.Context;
import android.security.keystore.UserNotAuthenticatedException;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.InvalidKeyException;
import java.security.UnrecoverableKeyException;
import java.util.Arrays;
import javax.crypto.BadPaddingException;

/** Pico JNI transport for the pinned PX-15 v001 contract, not a shared schema. */
public final class PicoAccountStoreBridge {
    static final int OK = 0, ABSENT = 1, LOCKED = 2, UNAVAILABLE = 3, CORRUPT = 4, IO_ERROR = 5;
    static final String SLOT = "account-map-v1";
    interface Backend {
        byte[] read() throws IOException, GeneralSecurityException;
        void write(byte[] bytes) throws IOException, GeneralSecurityException;
        void erase() throws IOException, GeneralSecurityException;
    }
    private final Backend backend;

    public PicoAccountStoreBridge(Context context) {
        SecureAccountStore store = new SecureAccountStore(context.getApplicationContext());
        backend = new Backend() {
            public byte[] read() throws IOException, GeneralSecurityException { return store.read(SLOT); }
            public void write(byte[] bytes) throws IOException, GeneralSecurityException { store.write(SLOT, bytes); }
            public void erase() throws IOException, GeneralSecurityException { store.remove(SLOT); }
        };
    }
    // Package-private injection seam: only tests supply a substitute backend.
    PicoAccountStoreBridge(Backend backend) { this.backend = backend; }

    public static final class ReadResult {
        public final int status;
        public final byte[] bytes;
        ReadResult(int status, byte[] bytes) { this.status = status; this.bytes = bytes; }
        public void clear() { if (bytes != null) Arrays.fill(bytes, (byte) 0); }
    }

    public synchronized ReadResult read() {
        byte[] bytes = null;
        try {
            bytes = backend.read();
            if (bytes == null) return new ReadResult(ABSENT, null);
            if (bytes.length == 0 || bytes.length > ProtectedRecordCodec.MAX_PLAINTEXT) {
                Arrays.fill(bytes, (byte) 0);
                return new ReadResult(CORRUPT, null);
            }
            return new ReadResult(OK, bytes);
        } catch (IOException | GeneralSecurityException | RuntimeException error) {
            if (bytes != null) Arrays.fill(bytes, (byte) 0);
            return new ReadResult(failure(error), null);
        }
    }

    public synchronized int write(byte[] bytes) {
        try {
            if (bytes == null || bytes.length == 0 || bytes.length > ProtectedRecordCodec.MAX_PLAINTEXT) {
                return CORRUPT;
            }
            backend.write(bytes);
            return OK;
        } catch (IOException | GeneralSecurityException | RuntimeException error) {
            return failure(error);
        } finally {
            if (bytes != null) Arrays.fill(bytes, (byte) 0);
        }
    }

    public synchronized int erase() {
        try { backend.erase(); return OK; }
        catch (IOException | GeneralSecurityException | RuntimeException error) { return failure(error); }
    }

    static int failure(Exception error) {
        if (error instanceof UserNotAuthenticatedException) return LOCKED;
        if (error instanceof ProtectedRecordCodec.InvalidRecordException
                || error instanceof InvalidKeyException || error instanceof UnrecoverableKeyException
                || error instanceof BadPaddingException || error instanceof IllegalArgumentException) return CORRUPT;
        if (error instanceof IOException) return IO_ERROR;
        // No message/classname/stack trace crosses this boundary. Unknown facility
        // errors stay unavailable, never absent or evidence that the device is locked.
        return UNAVAILABLE;
    }
}
