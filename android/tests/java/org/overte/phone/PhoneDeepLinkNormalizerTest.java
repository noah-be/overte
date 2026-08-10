package org.overte.phone;

/** Dependency-free JVM regression tests for exported Android deep links. */
public final class PhoneDeepLinkNormalizerTest {
    private static int assertions;

    public static void main(String[] arguments) {
        acceptsAndCanonicalizesSupportedSchemes();
        preservesEncodedPayload();
        rejectsUnsupportedOrMalformedSchemes();
        rejectsRawWhitespaceAndControlCharacters();
        enforcesLengthLimit();
        deterministicPropertyChecks();
        System.out.println("PhoneDeepLinkNormalizerTest: " + assertions + " assertions passed");
    }

    private static void acceptsAndCanonicalizesSupportedSchemes() {
        expect("hifi://example.com/path", "hifi://example.com/path");
        expect("hifi://example.com/path", "overte://example.com/path");
        expect("hifi://example.com/path", "OvErTe://example.com/path");
        expect("hifi:/42,10,-7", "HIFI:/42,10,-7");
        expect("hifi:", "overte:");
    }

    private static void preservesEncodedPayload() {
        expect("hifi://example.com/a%20b?name=x%09y#z%0Aq",
                "overte://example.com/a%20b?name=x%09y#z%0Aq");
        expect("hifi://example.com/%2F%3A", "hifi://example.com/%2F%3A");
    }

    private static void rejectsUnsupportedOrMalformedSchemes() {
        reject(null);
        reject("");
        reject("example.com/no-scheme");
        reject("https://example.com");
        reject("overtex://example.com");
    }

    private static void rejectsRawWhitespaceAndControlCharacters() {
        reject(" overte://example.com");
        reject("overte://example.com/a b");
        reject("overte://example.com/a\tb");
        reject("overte://example.com/a\nb");
        reject("overte://example.com/a\u00a0b");
        reject("overte://example.com/a\u0000b");
    }

    private static void enforcesLengthLimit() {
        String prefix = "overte:";
        String maximum = prefix + repeat('a', PhoneDeepLinkNormalizer.MAX_URL_LENGTH - prefix.length());
        expect("hifi:" + maximum.substring(prefix.length()), maximum);
        reject(maximum + "a");
    }

    /** Fixed-seed generated cases catch boundary regressions without flaky random input. */
    private static void deterministicPropertyChecks() {
        long state = 0x4f56455254454cL;
        String alphabet = "abcdefghijklmnopqrstuvwxyz0123456789-._~/%?=&+#";
        for (int caseIndex = 0; caseIndex < 512; ++caseIndex) {
            StringBuilder payload = new StringBuilder();
            int length = 1 + (int) (state & 63);
            for (int index = 0; index < length; ++index) {
                state = state * 6364136223846793005L + 1442695040888963407L;
                payload.append(alphabet.charAt((int) ((state >>> 1) % alphabet.length())));
            }
            String scheme = (caseIndex & 1) == 0 ? "overte:" : "hifi:";
            String input = scheme + payload;
            expect("hifi:" + payload, input);

            int insertion = (int) ((state >>> 1) % (input.length() + 1));
            char unsafe = (caseIndex & 1) == 0 ? '\n' : '\u00a0';
            reject(input.substring(0, insertion) + unsafe + input.substring(insertion));
        }
    }

    private static String repeat(char value, int count) {
        StringBuilder result = new StringBuilder(count);
        while (result.length() < count) {
            result.append(value);
        }
        return result.toString();
    }

    private static void reject(String input) {
        expect(null, input);
    }

    private static void expect(String expected, String input) {
        ++assertions;
        String actual = PhoneDeepLinkNormalizer.normalize(input);
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError("input=" + printable(input)
                    + " expected=" + printable(expected)
                    + " actual=" + printable(actual));
        }
    }

    private static String printable(String value) {
        return value == null ? "<null>" : '"' + value.replace("\n", "\\n").replace("\t", "\\t") + '"';
    }
}
