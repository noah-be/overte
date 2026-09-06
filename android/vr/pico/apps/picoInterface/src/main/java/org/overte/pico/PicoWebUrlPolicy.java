// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Per-surface URL policy; grants no bridge, file, content or external-app access. */
final class PicoWebUrlPolicy {
    private static final int MAX_LOCAL_DOCUMENT = 1024 * 1024;
    private PicoWebUrlPolicy() { }

    static String navigation(String input) {
        if (input == null || input.isEmpty() || input.equals("about:blank")) return "about:blank";
        if (input.length() > MAX_LOCAL_DOCUMENT) return null;
        String lower = input.toLowerCase(Locale.ROOT);
        if (lower.startsWith("data:text/html,") || lower.startsWith("data:text/html;")) {
            int comma = input.indexOf(',');
            if (comma < 0) return null;
            String media = lower.substring(0, comma);
            if (!media.matches("data:text/html(?:;charset=utf-8)?(?:;base64)?")) return null;
            for (int index = 0; index < input.length(); index++) {
                if (Character.isISOControl(input.charAt(index))) return null;
            }
            return input;
        }
        String target = PicoRestartUrlPolicy.worldUrl(input);
        if (target == null) return null;
        return target.startsWith("http://") || target.startsWith("https://") ? target : null;
    }

    static boolean resource(String input) {
        if (input == null) return false;
        try {
            URI uri = new URI(input);
            String scheme = uri.getScheme();
            if (scheme == null) return false;
            if (scheme.equalsIgnoreCase("http") || scheme.equalsIgnoreCase("https")) {
                return navigation(input) != null;
            }
            // WebView handles inline data locally; it receives no OS file/content grant.
            return scheme.equalsIgnoreCase("data") && input.length() <= MAX_LOCAL_DOCUMENT;
        } catch (URISyntaxException error) {
            return false;
        }
    }
}
