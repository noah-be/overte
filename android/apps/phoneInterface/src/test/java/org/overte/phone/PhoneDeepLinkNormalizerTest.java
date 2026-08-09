package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import org.junit.Test;

public final class PhoneDeepLinkNormalizerTest {
    @Test
    public void canonicalizesBothSupportedSchemesWithoutChangingPayload() {
        assertEquals("hifi://example.com/a%20b?x=%09",
                PhoneDeepLinkNormalizer.normalize("overte://example.com/a%20b?x=%09"));
        assertEquals("hifi:/1,2,3", PhoneDeepLinkNormalizer.normalize("HiFi:/1,2,3"));
    }

    @Test
    public void rejectsMalformedUnsupportedAndUnsafeValues() {
        assertNull(PhoneDeepLinkNormalizer.normalize(null));
        assertNull(PhoneDeepLinkNormalizer.normalize(""));
        assertNull(PhoneDeepLinkNormalizer.normalize("missing-scheme-separator"));
        assertNull(PhoneDeepLinkNormalizer.normalize("://missing-scheme"));
        assertNull(PhoneDeepLinkNormalizer.normalize("https://example.com"));
        assertNull(PhoneDeepLinkNormalizer.normalize("overte://example.com/a b"));
        assertNull(PhoneDeepLinkNormalizer.normalize("overte://example.com/a\nb"));
    }

    @Test
    public void rejectsEveryRawAsciiControlCharacter() {
        for (char character = 0; character < 32; ++character) {
            assertNull("control U+" + String.format("%04X", (int) character),
                    PhoneDeepLinkNormalizer.normalize("overte://host/a" + character + "b"));
        }
        assertNull(PhoneDeepLinkNormalizer.normalize("overte://host/a\u007fb"));
    }

    @Test
    public void rejectsUnicodeWhitespaceAndSpaceCharacters() {
        char[] unsafe = { '\u00a0', '\u1680', '\u2000', '\u2007', '\u2028', '\u202f', '\u205f', '\u3000' };
        for (char character : unsafe) {
            assertNull("space U+" + String.format("%04X", (int) character),
                    PhoneDeepLinkNormalizer.normalize("hifi://host/a" + character + "b"));
        }
    }

    @Test
    public void preservesOpaqueHierarchicalAndEncodedPayloadsExactly() {
        String[] inputs = {
            "overte:", "overte:/1,2,3", "overte://host",
            "overte://host/%2f%2F?x=a%20b#%00", "hifi:opaque:value:with:colons"
        };
        for (String input : inputs) {
            assertEquals("hifi" + input.substring(input.indexOf(':')),
                    PhoneDeepLinkNormalizer.normalize(input));
        }
    }

    @Test
    public void schemeMatchingDoesNotAcceptPrefixesOrSuffixes() {
        assertNull(PhoneDeepLinkNormalizer.normalize("overte-extra://host"));
        assertNull(PhoneDeepLinkNormalizer.normalize("xoverte://host"));
        assertNull(PhoneDeepLinkNormalizer.normalize(":overte://host"));
    }

    @Test
    public void enforcesMaximumLength() {
        String maximum = "overte:" + repeat('a',
                PhoneDeepLinkNormalizer.MAX_URL_LENGTH - "overte:".length());
        assertEquals("hifi:" + maximum.substring("overte:".length()),
                PhoneDeepLinkNormalizer.normalize(maximum));
        assertNull(PhoneDeepLinkNormalizer.normalize(maximum + "a"));
    }

    private static String repeat(char value, int count) {
        StringBuilder result = new StringBuilder(count);
        while (result.length() < count) {
            result.append(value);
        }
        return result.toString();
    }
}
