package io.highfidelity.hifiinterface.task;

import java.io.IOException;
import java.io.InputStream;
import java.net.URLConnection;
import java.util.Objects;

import io.highfidelity.hifiinterface.LegacyAssetTextPolicy;

/** Bounded network and input ownership policy for legacy profile HTML. */
public final class LegacyProfilePagePolicy {
    public static final int CONNECT_TIMEOUT_MILLIS = 10_000;
    public static final int READ_TIMEOUT_MILLIS = 15_000;

    private LegacyProfilePagePolicy() {
    }

    public static String read(URLConnection connection) throws IOException {
        Objects.requireNonNull(connection, "connection");
        connection.setConnectTimeout(CONNECT_TIMEOUT_MILLIS);
        connection.setReadTimeout(READ_TIMEOUT_MILLIS);
        try (InputStream input = connection.getInputStream()) {
            return LegacyAssetTextPolicy.readUtf8(
                    input, LegacyAssetTextPolicy.MAX_ASSET_TEXT_BYTES);
        }
    }
}
