package io.highfidelity.hifiinterface;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public final class LegacyAssetTextPolicy {
    public static final int MAX_ASSET_TEXT_BYTES = 1024 * 1024;

    private LegacyAssetTextPolicy() {
    }

    public static String readUtf8(InputStream input, int maxBytes) throws IOException {
        Objects.requireNonNull(input, "input");
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes must not be negative");
        }
        ByteArrayOutputStream output = new ByteArrayOutputStream(Math.min(maxBytes, 8192));
        byte[] buffer = new byte[8192];
        int total = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            if (count == 0) {
                continue;
            }
            if (count > maxBytes - total) {
                throw new IOException("asset text exceeds the configured size limit");
            }
            output.write(buffer, 0, count);
            total += count;
        }
        return new String(output.toByteArray(), StandardCharsets.UTF_8);
    }
}
