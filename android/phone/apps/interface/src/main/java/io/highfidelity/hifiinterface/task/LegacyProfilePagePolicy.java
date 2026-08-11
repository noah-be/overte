package io.highfidelity.hifiinterface.task;

import java.io.IOException;
import java.io.InputStream;
import java.net.URLConnection;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import io.highfidelity.hifiinterface.LegacyAssetTextPolicy;

/** Bounded network and input ownership policy for legacy profile HTML. */
public final class LegacyProfilePagePolicy {
    public static final int CONNECT_TIMEOUT_MILLIS = 10_000;
    public static final int READ_TIMEOUT_MILLIS = 15_000;
    private static final Pattern IMAGE_TAG = Pattern.compile(
            "<img\\b[^>]*>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern QUOTED_ATTRIBUTE = Pattern.compile(
            "([A-Za-z_:][A-Za-z0-9_:.-]*)\\s*=\\s*(['\"])(.*?)\\2",
            Pattern.CASE_INSENSITIVE | Pattern.DOTALL);

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

    public static String extractProfileImageUrl(String html) {
        if (html == null || html.isEmpty()) {
            return null;
        }
        Matcher tags = IMAGE_TAG.matcher(html);
        while (tags.find()) {
            String classValue = null;
            String source = null;
            Matcher attributes = QUOTED_ATTRIBUTE.matcher(tags.group());
            while (attributes.find()) {
                String name = attributes.group(1);
                String value = attributes.group(3);
                if ("class".equalsIgnoreCase(name)) {
                    classValue = value;
                } else if ("src".equalsIgnoreCase(name)) {
                    source = value;
                }
            }
            if (source != null && !source.isEmpty() && hasClassToken(classValue, "users-img")) {
                return source;
            }
        }
        return null;
    }

    private static boolean hasClassToken(String classes, String expected) {
        if (classes == null) {
            return false;
        }
        for (String token : classes.trim().split("\\s+")) {
            if (expected.equals(token)) {
                return true;
            }
        }
        return false;
    }
}
