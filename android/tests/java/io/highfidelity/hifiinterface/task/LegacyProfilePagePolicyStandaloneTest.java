package io.highfidelity.hifiinterface.task;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;

import io.highfidelity.hifiinterface.LegacyAssetTextPolicy;

public final class LegacyProfilePagePolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class TrackingInputStream extends InputStream {
        private final ByteArrayInputStream delegate;
        private boolean closed;
        private final boolean fail;

        TrackingInputStream(byte[] payload, boolean fail) {
            delegate = new ByteArrayInputStream(payload);
            this.fail = fail;
        }

        @Override
        public int read() throws IOException {
            if (fail) {
                throw new IOException("fixture read failure");
            }
            return delegate.read();
        }

        @Override
        public int read(byte[] target, int offset, int length) throws IOException {
            if (fail) {
                throw new IOException("fixture read failure");
            }
            return delegate.read(target, offset, Math.min(length, 3));
        }

        @Override
        public void close() throws IOException {
            closed = true;
            delegate.close();
        }
    }

    private static final class Connection extends URLConnection {
        private final TrackingInputStream input;
        private boolean timeoutsSetBeforeOpen;

        Connection(TrackingInputStream input) throws Exception {
            super(new URL("https://example.invalid/profile"));
            this.input = input;
        }

        @Override
        public void connect() {
        }

        @Override
        public InputStream getInputStream() {
            timeoutsSetBeforeOpen = getConnectTimeout()
                    == LegacyProfilePagePolicy.CONNECT_TIMEOUT_MILLIS
                    && getReadTimeout() == LegacyProfilePagePolicy.READ_TIMEOUT_MILLIS;
            return input;
        }
    }

    public static void main(String[] args) throws Exception {
        TrackingInputStream unicode = new TrackingInputStream(
                "Grüße 🚲".getBytes(StandardCharsets.UTF_8), false);
        Connection connection = new Connection(unicode);
        check("Grüße 🚲".equals(LegacyProfilePagePolicy.read(connection)),
                "profile pages must use bounded UTF-8 reads");
        check(connection.timeoutsSetBeforeOpen, "timeouts must be set before opening the stream");
        check(unicode.closed, "successful reads must close their stream");

        TrackingInputStream failure = new TrackingInputStream(new byte[] { 1 }, true);
        try {
            LegacyProfilePagePolicy.read(new Connection(failure));
            throw new AssertionError("read failures must propagate");
        } catch (IOException expected) {
            assertions++;
        }
        check(failure.closed, "failed reads must close their stream");

        byte[] atLimit = new byte[LegacyAssetTextPolicy.MAX_ASSET_TEXT_BYTES];
        TrackingInputStream exact = new TrackingInputStream(atLimit, false);
        check(LegacyProfilePagePolicy.read(new Connection(exact)).length() == atLimit.length,
                "a response exactly at the size limit must pass");
        check(exact.closed, "limit-sized reads must close their stream");

        TrackingInputStream oversized = new TrackingInputStream(
                new byte[LegacyAssetTextPolicy.MAX_ASSET_TEXT_BYTES + 1], false);
        try {
            LegacyProfilePagePolicy.read(new Connection(oversized));
            throw new AssertionError("oversized responses must fail");
        } catch (IOException expected) {
            assertions++;
        }
        check(oversized.closed, "oversized reads must close their stream");

        try {
            LegacyProfilePagePolicy.read(null);
            throw new AssertionError("null connections must fail");
        } catch (NullPointerException expected) {
            assertions++;
        }
        System.out.println("LegacyProfilePagePolicyStandaloneTest: " + assertions
                + " assertions passed");
    }
}
