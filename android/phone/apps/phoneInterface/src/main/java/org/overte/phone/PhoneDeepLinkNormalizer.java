package org.overte.phone;

/** Pure Java validation for URLs received at the Android application boundary. */
final class PhoneDeepLinkNormalizer {
    static final int MAX_URL_LENGTH = 4096;

    private PhoneDeepLinkNormalizer() {
    }

    static String normalize(String value) {
        if (value == null || value.isEmpty() || value.length() > MAX_URL_LENGTH
                || containsUnsafeCharacter(value)) {
            return null;
        }

        int schemeSeparator = value.indexOf(':');
        if (schemeSeparator < 0) {
            return null;
        }

        String scheme = value.substring(0, schemeSeparator);
        if (!"overte".equalsIgnoreCase(scheme) && !"hifi".equalsIgnoreCase(scheme)) {
            return null;
        }

        // The native address path uses the established hifi scheme. Preserve
        // the encoded URI payload byte-for-byte while canonicalizing its alias.
        return "hifi" + value.substring(schemeSeparator);
    }

    private static boolean containsUnsafeCharacter(String value) {
        for (int index = 0; index < value.length(); ++index) {
            char character = value.charAt(index);
            // QtActivityLoader treats ASCII spaces as argv separators. Reject
            // all raw whitespace rather than trying to quote untrusted input;
            // percent-encoded whitespace remains valid URI data.
            if (Character.isISOControl(character)
                    || Character.isWhitespace(character)
                    || Character.isSpaceChar(character)) {
                return true;
            }
        }
        return false;
    }
}
