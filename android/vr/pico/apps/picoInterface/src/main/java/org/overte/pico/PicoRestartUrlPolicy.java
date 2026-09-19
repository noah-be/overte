// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import java.net.IDN;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Locale;

/** Native Java decision used before persisting or consuming a private restart. */
final class PicoRestartUrlPolicy {
    static final int MAX_URL_BYTES = 4096;
    static final String BASE = "--display=OpenXR";
    private static final String PREFIX = BASE + " --url ";

    private PicoRestartUrlPolicy() { }

    static String arguments(String value) {
        if (BASE.equals(value)) return BASE;
        if (value == null || !value.startsWith(PREFIX)) return null;
        String url = worldUrl(value.substring(PREFIX.length()));
        return url == null ? null : PREFIX + url;
    }

    static String worldUrl(String value) {
        if (value == null || value.isEmpty() || value.length() > MAX_URL_BYTES) return null;
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFC);
        if (!safeText(normalized) || normalized.getBytes(StandardCharsets.UTF_8).length > MAX_URL_BYTES) {
            return null;
        }
        try {
            URI parsed = new URI(normalized);
            if (parsed.isOpaque() || parsed.getScheme() == null) return null;
            String scheme = parsed.getScheme().toLowerCase(Locale.ROOT);
            if (!scheme.equals("hifi") && !scheme.equals("http")
                    && !scheme.equals("https") && !scheme.equals("file")) return null;
            String authority = parsed.getRawAuthority();
            if (parsed.getRawUserInfo() != null || (authority != null
                    && (authority.contains("@") || authority.contains("%")))) return null;
            if (!safeText(parsed.getPath()) || !safeText(parsed.getQuery())
                    || !safeText(parsed.getFragment())) return null;
            if (scheme.equals("file")) {
                if (authority != null && !authority.equalsIgnoreCase("localhost")) return null;
                if (parsed.getPath() == null || !parsed.getPath().startsWith("/")) return null;
                for (String part : parsed.getPath().split("/")) {
                    if (part.equals("..")) return null;
                }
            } else {
                if (authority == null || authority.isEmpty()) return null;
                if (parsed.getHost() == null) {
                    // Support Unicode DNS labels using the platform IDN implementation.
                    if (authority.contains(":")) return null;
                    authority = IDN.toASCII(authority, IDN.USE_STD3_ASCII_RULES).toLowerCase(Locale.ROOT);
                } else {
                    if (parsed.getPort() < -1 || parsed.getPort() > 65535) return null;
                    authority = authority.toLowerCase(Locale.ROOT);
                }
            }
            String suffix = normalized.substring(normalized.indexOf(':') + 1);
            if (parsed.getRawAuthority() != null) {
                suffix = "//" + authority + suffix.substring(2 + parsed.getRawAuthority().length());
            }
            String encoded = new URI(scheme + ":" + suffix).toASCIIString();
            return encoded.getBytes(StandardCharsets.UTF_8).length <= MAX_URL_BYTES ? encoded : null;
        } catch (URISyntaxException | IllegalArgumentException error) {
            return null;
        }
    }

    private static boolean safeText(String value) {
        if (value == null) return true;
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            if (Character.isHighSurrogate(current)) {
                if (++index >= value.length() || !Character.isLowSurrogate(value.charAt(index))) return false;
            } else if (Character.isLowSurrogate(current)) {
                return false;
            }
            if (Character.isISOControl(current) || current == '\\'
                    || current == 0x061c || current == 0x200e || current == 0x200f
                    || (current >= 0x202a && current <= 0x202e)
                    || (current >= 0x2066 && current <= 0x2069)) return false;
        }
        return true;
    }
}
