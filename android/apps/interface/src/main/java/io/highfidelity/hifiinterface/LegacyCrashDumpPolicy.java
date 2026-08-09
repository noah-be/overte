package io.highfidelity.hifiinterface;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.UnsupportedEncodingException;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLEncoder;
import java.util.Objects;

public final class LegacyCrashDumpPolicy {
    public static final long MAX_DUMP_BYTES = 256L * 1024L * 1024L;
    public static final int CONNECT_TIMEOUT_MILLIS = 10_000;
    public static final int READ_TIMEOUT_MILLIS = 15_000;

    private LegacyCrashDumpPolicy() {
    }

    public static boolean isAcceptedLength(long length) {
        return length > 0 && length <= MAX_DUMP_BYTES;
    }

    public static boolean isSuccessfulUploadStatus(int status) {
        return status >= 200 && status < 300;
    }

    public static void configureUploadConnection(URLConnection connection) {
        Objects.requireNonNull(connection, "connection");
        connection.setConnectTimeout(CONNECT_TIMEOUT_MILLIS);
        connection.setReadTimeout(READ_TIMEOUT_MILLIS);
    }

    public static URL buildUploadUrl(String baseUrl, String token, String encodedAnnotations)
            throws MalformedURLException {
        if (baseUrl == null || baseUrl.trim().isEmpty()) {
            throw new MalformedURLException("crash upload base URL is missing");
        }
        URL parsed = new URL(baseUrl.trim());
        if (!"https".equalsIgnoreCase(parsed.getProtocol())
                || parsed.getHost() == null || parsed.getHost().isEmpty()
                || parsed.getQuery() != null || parsed.getRef() != null
                || parsed.getUserInfo() != null) {
            throw new MalformedURLException("crash upload base URL is unsafe");
        }
        String path = parsed.getPath() == null ? "" : parsed.getPath();
        while (path.endsWith("/")) {
            path = path.substring(0, path.length() - 1);
        }
        String encodedToken;
        try {
            encodedToken = URLEncoder.encode(token == null ? "" : token, "UTF-8");
        } catch (UnsupportedEncodingException impossible) {
            throw new AssertionError("UTF-8 is unavailable", impossible);
        }
        String query = "format=minidump&token=" + encodedToken;
        if (encodedAnnotations != null && !encodedAnnotations.isEmpty()) {
            query += "&" + encodedAnnotations;
        }
        return new URL("https", parsed.getHost(), parsed.getPort(), path + "/post?" + query);
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
