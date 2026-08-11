package io.highfidelity.hifiinterface;

import java.util.Locale;

public final class LegacyDomainLocationPolicy {
    private LegacyDomainLocationPolicy() {
    }

    public static String rootPrefix(String location) {
        if (location == null) {
            return null;
        }
        String value = location.trim();
        int schemeEnd = value.indexOf("://");
        if (schemeEnd <= 0) {
            return null;
        }
        int authorityStart = schemeEnd + 3;
        int authorityEnd = value.length();
        for (char delimiter : new char[] { '/', '?', '#' }) {
            int candidate = value.indexOf(delimiter, authorityStart);
            if (candidate >= 0 && candidate < authorityEnd) {
                authorityEnd = candidate;
            }
        }
        if (authorityEnd == authorityStart) {
            return null;
        }
        return value.substring(0, authorityEnd).toLowerCase(Locale.ROOT) + "/";
    }

    public static boolean matchesRoot(String location, String candidate) {
        String locationRoot = rootPrefix(location);
        String candidateRoot = rootPrefix(candidate);
        return locationRoot != null && locationRoot.equals(candidateRoot);
    }
}
