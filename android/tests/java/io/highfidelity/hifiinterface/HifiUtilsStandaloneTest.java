package io.highfidelity.hifiinterface;

/** Dependency-free regression and fixed-seed property tests for legacy URL handling. */
public final class HifiUtilsStandaloneTest {
    private static int assertions;

    public static void main(String[] arguments) {
        HifiUtils subject = HifiUtils.getInstance();
        same(subject, HifiUtils.getInstance());
        expect("", subject.sanitizeHifiUrl(null));
        expect("", subject.sanitizeHifiUrl(" \n\t "));
        expect("hifi://welcome.overte.org/path", subject.sanitizeHifiUrl(" welcome.overte.org/path "));
        expect("https://example.test/a", subject.sanitizeHifiUrl("https://example.test/a"));
        expect("bad uri [", subject.sanitizeHifiUrl(" bad uri [ "));

        expect("", subject.absoluteHifiAssetUrl(null));
        expect("", subject.absoluteHifiAssetUrl(" \t "));
        expect(HifiUtils.METAVERSE_BASE_URL + "/asset", subject.absoluteHifiAssetUrl(" /asset "));
        expect("https://base/assets/image.png",
                subject.absoluteHifiAssetUrl("assets/image.png", "https://base"));
        expect("https://base/assets/image.png",
                subject.absoluteHifiAssetUrl("/assets/image.png", "https://base/"));
        expect("assets/image.png", subject.absoluteHifiAssetUrl("assets/image.png", null));
        expect("assets/image.png", subject.absoluteHifiAssetUrl("assets/image.png", " \t "));
        expect("https://base.test/avatar.png",
                subject.absoluteHifiAssetUrl(" avatar.png ", "https://base.test/"));
        expect("atp:/hash", subject.absoluteHifiAssetUrl("atp:/hash", "https://base.test/"));
        expect("bad uri [", subject.absoluteHifiAssetUrl(" bad uri [ ", "https://base.test/"));
        fixedSeedBareAddresses(subject);
        System.out.println("HifiUtilsStandaloneTest: " + assertions + " assertions passed");
    }

    private static void fixedSeedBareAddresses(HifiUtils subject) {
        long state = 0x4849464955524cL;
        for (int index = 0; index < 512; ++index) {
            state = state * 6364136223846793005L + 1442695040888963407L;
            String payload = "domain" + Long.toUnsignedString(state >>> 1, 36) + ".test/path/" + index;
            String input = ((index & 1) == 0 ? " " : "\t") + payload
                    + ((index & 2) == 0 ? "\n" : "  ");
            expect("hifi://" + payload, subject.sanitizeHifiUrl(input));
            expect("https://base/" + payload,
                    subject.absoluteHifiAssetUrl(input, "https://base/"));
        }
    }

    private static void same(Object expected, Object actual) {
        ++assertions;
        if (expected != actual) {
            throw new AssertionError("singleton identity changed");
        }
    }

    private static void expect(String expected, String actual) {
        ++assertions;
        if (!expected.equals(actual)) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }
}
