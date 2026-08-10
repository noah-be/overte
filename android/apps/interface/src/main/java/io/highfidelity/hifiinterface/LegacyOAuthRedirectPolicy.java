package io.highfidelity.hifiinterface;

import java.net.URI;
import java.net.URISyntaxException;

/** Exact trust boundary for legacy OAuth redirect callbacks. */
public final class LegacyOAuthRedirectPolicy {
    private LegacyOAuthRedirectPolicy() {
    }

    public static boolean matches(String configured, String candidate) {
        if (configured == null || candidate == null
                || configured.trim().isEmpty() || candidate.trim().isEmpty()) {
            return false;
        }
        try {
            URI expected = new URI(configured);
            URI actual = new URI(candidate);
            if (!isSafeAbsoluteRedirect(expected) || !isSafeAbsoluteRedirect(actual)
                    || expected.getRawQuery() != null || expected.getRawFragment() != null
                    || actual.getRawFragment() != null) {
                return false;
            }
            return expected.getScheme().equalsIgnoreCase(actual.getScheme())
                    && expected.getHost().equalsIgnoreCase(actual.getHost())
                    && expected.getPort() == actual.getPort()
                    && rawPath(expected).equals(rawPath(actual));
        } catch (URISyntaxException error) {
            return false;
        }
    }

    private static boolean isSafeAbsoluteRedirect(URI value) {
        return value.isAbsolute() && !value.isOpaque()
                && value.getScheme() != null && value.getHost() != null
                && !value.getHost().isEmpty() && value.getRawUserInfo() == null;
    }

    private static String rawPath(URI value) {
        return value.getRawPath() == null ? "" : value.getRawPath();
    }
}
