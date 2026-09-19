// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import java.io.IOException;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import android.security.keystore.UserNotAuthenticatedException;

/** Fault backend only; JNI and PicoAccountStoreBridge under test are production code. */
public final class PicoAccountBridgeTest {
    private static int mode;
    private static byte[] stored, lastRead, lastWrite;
    public static void setMode(int value) { mode = value; }
    private static void fault() throws IOException, GeneralSecurityException {
        switch (mode) {
            case 2: throw new IOException("private fixture must not reach diagnostics");
            case 3: throw new UserNotAuthenticatedException();
            case 4: throw new ProtectedRecordCodec.InvalidRecordException();
            case 5: throw new GeneralSecurityException("private fixture");
            case 6: throw new IllegalStateException("private fixture");
            case 8: throw new AssertionError("private fixture JNI exception");
            default: break;
        }
    }
    public static PicoAccountStoreBridge create() {
        return new PicoAccountStoreBridge(new PicoAccountStoreBridge.Backend() {
            public byte[] read() throws IOException, GeneralSecurityException {
                fault();
                lastRead = mode == 7 ? new byte[0] : stored == null ? null : stored.clone();
                return lastRead;
            }
            public void write(byte[] bytes) throws IOException, GeneralSecurityException {
                lastWrite = bytes;
                fault(); stored = bytes.clone();
            }
            public void erase() throws IOException, GeneralSecurityException { fault(); stored = null; }
        });
    }
    public static boolean buffersCleared() {
        for (byte[] bytes : new byte[][] { lastRead, lastWrite }) {
            if (bytes != null) for (byte value : bytes) if (value != 0) return false;
        }
        return true;
    }
    public static void main(String[] args) {
        PicoAccountStoreBridge bridge = create();
        if (bridge.read().status != PicoAccountStoreBridge.ABSENT) throw new AssertionError();
        byte[] original = {1,2,3};
        if (bridge.write(original) != PicoAccountStoreBridge.OK || !buffersCleared()) throw new AssertionError();
        PicoAccountStoreBridge.ReadResult result = bridge.read();
        if (!Arrays.equals(result.bytes, new byte[] {1,2,3})) throw new AssertionError();
        result.clear();
        if (!buffersCleared()) throw new AssertionError();
        for (int value : new int[] {2,3,4,5,6,7}) {
            setMode(value);
            int expected = value == 2 ? 5 : value == 3 ? 2 : value == 4 || value == 7 ? 4 : 3;
            result = bridge.read();
            if (result.status != expected || result.bytes != null) throw new AssertionError("read status " + value);
        }
        setMode(0);
        if (bridge.write(new byte[0]) != 4 || bridge.write(null) != 4
                || bridge.write(new byte[1024*1024+1]) != 4 || bridge.erase() != 0
                || bridge.read().status != 1) throw new AssertionError();
        System.out.println("Pico production Java account bridge status/bounds/clearing PASS (test backend)");
    }
}
