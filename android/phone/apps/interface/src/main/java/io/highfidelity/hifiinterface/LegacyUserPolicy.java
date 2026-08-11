package io.highfidelity.hifiinterface;

public final class LegacyUserPolicy {
    private LegacyUserPolicy() {
    }

    public static boolean isUsablePage(boolean successful, boolean bodyPresent,
            boolean dataPresent, boolean usersPresent, int totalEntries) {
        return successful && bodyPresent && dataPresent && usersPresent && totalEntries >= 0;
    }

    public static String safeText(String value) {
        return value == null ? "" : value;
    }

    public static boolean hasText(String value) {
        return value != null && !value.trim().isEmpty();
    }

    public static boolean isFriend(String connection) {
        return "friend".equals(connection);
    }

    public static String locationName(String rootName, String domainName) {
        if (hasText(rootName)) {
            return rootName;
        }
        return safeText(domainName);
    }
}
