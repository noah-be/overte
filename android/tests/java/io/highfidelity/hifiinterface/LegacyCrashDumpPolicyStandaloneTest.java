package io.highfidelity.hifiinterface;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLDecoder;
import java.net.URLConnection;
import java.util.Arrays;

public final class LegacyCrashDumpPolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class Connection extends URLConnection {
        private boolean opened;
        private boolean configuredBeforeOpen;

        Connection() throws Exception {
            super(new URL("https://crash.example.test/post"));
        }

        @Override
        public void connect() {
            opened = true;
            configuredBeforeOpen = getConnectTimeout()
                    == LegacyCrashDumpPolicy.CONNECT_TIMEOUT_MILLIS
                    && getReadTimeout() == LegacyCrashDumpPolicy.READ_TIMEOUT_MILLIS;
        }
    }

    public static void main(String[] args) throws Exception {
        check(!LegacyCrashDumpPolicy.isAcceptedLength(-1), "negative lengths must fail");
        check(LegacyCrashDumpPolicy.isAcceptedLength(0), "empty dumps are bounded");
        check(LegacyCrashDumpPolicy.isAcceptedLength(LegacyCrashDumpPolicy.MAX_DUMP_BYTES),
                "the exact maximum must pass");
        check(!LegacyCrashDumpPolicy.isAcceptedLength(LegacyCrashDumpPolicy.MAX_DUMP_BYTES + 1),
                "lengths above the maximum must fail");

        Connection uploadConnection = new Connection();
        LegacyCrashDumpPolicy.configureUploadConnection(uploadConnection);
        check(LegacyCrashDumpPolicy.CONNECT_TIMEOUT_MILLIS > 0
                        && LegacyCrashDumpPolicy.READ_TIMEOUT_MILLIS > 0,
                "upload timeouts must be positive");
        uploadConnection.connect();
        check(uploadConnection.opened && uploadConnection.configuredBeforeOpen,
                "upload timeouts must be installed before connection or stream access");
        try {
            LegacyCrashDumpPolicy.configureUploadConnection(null);
            throw new AssertionError("null upload connections must fail");
        } catch (NullPointerException expected) {
            assertions++;
        }

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

        URL basic = LegacyCrashDumpPolicy.buildUploadUrl(
                "https://crash.example.test/", "token", "build=1&platform=android");
        check("https://crash.example.test/post".equals(
                        basic.getProtocol() + "://" + basic.getAuthority() + basic.getPath()),
                "the upload path must contain exactly one slash before post");
        check(basic.getQuery().startsWith("format=minidump&token=token&build=1"),
                "encoded annotations must follow fixed parameters");

        String adversarialToken = "a+b&c=d /ü%#";
        URL encoded = LegacyCrashDumpPolicy.buildUploadUrl(
                "https://crash.example.test:8443/api///", adversarialToken, "");
        check("/api/post".equals(encoded.getPath()) && encoded.getPort() == 8443,
                "ports and base paths must be preserved while trailing slashes normalize");
        String encodedToken = encoded.getQuery().substring(
                encoded.getQuery().indexOf("token=") + "token=".length());
        check(adversarialToken.equals(URLDecoder.decode(encodedToken, "UTF-8")),
                "reserved token characters must round-trip as one query value");
        check(!encoded.getQuery().substring(encoded.getQuery().indexOf("token=")).contains("&"),
                "tokens must not inject additional query parameters");

        String[] unsafeBases = {
                null, "", "  ", "http://crash.example.test", "file:///tmp/dump",
                "https:///post", "https://crash.example.test?old=1",
                "https://crash.example.test#fragment", "https://user@crash.example.test"
        };
        for (String unsafe : unsafeBases) {
            try {
                LegacyCrashDumpPolicy.buildUploadUrl(unsafe, "token", "");
                throw new AssertionError("unsafe upload bases must fail");
            } catch (MalformedURLException expected) {
                assertions++;
            }
        }

        System.out.println("LegacyCrashDumpPolicyStandaloneTest: " + assertions
                + " assertions passed");
    }
}
