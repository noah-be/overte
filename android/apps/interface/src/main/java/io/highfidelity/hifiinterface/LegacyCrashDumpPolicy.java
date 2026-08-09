package io.highfidelity.hifiinterface;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Objects;

public final class LegacyCrashDumpPolicy {
    public static final long MAX_DUMP_BYTES = 256L * 1024L * 1024L;

    private LegacyCrashDumpPolicy() {
    }

    public static boolean isAcceptedLength(long length) {
        return length >= 0 && length <= MAX_DUMP_BYTES;
    }

    public static long copyBounded(InputStream input, OutputStream output, long maxBytes)
            throws IOException {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(output, "output");
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes must not be negative");
        }
        byte[] buffer = new byte[16 * 1024];
        long total = 0;
        while (true) {
            int count = input.read(buffer);
            if (count == -1) {
                return total;
            }
            if (count == 0) {
                int single = input.read();
                if (single == -1) {
                    return total;
                }
                if (total == maxBytes) {
                    throw new IOException("crash dump exceeds the configured size limit");
                }
                output.write(single);
                total++;
                continue;
            }
            if (count > maxBytes - total) {
                throw new IOException("crash dump exceeds the configured size limit");
            }
            output.write(buffer, 0, count);
            total += count;
        }
    }
}
