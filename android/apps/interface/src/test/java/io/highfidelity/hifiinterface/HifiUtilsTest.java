package io.highfidelity.hifiinterface;

import static org.junit.Assert.*;

import org.junit.Test;

import java.util.Random;

public final class HifiUtilsTest {
    private final HifiUtils subject = HifiUtils.getInstance();

    @Test public void sanitizeAddsHifiSchemeToBareAddress() {
        assertEquals("hifi://welcome.overte.org/1,2,3", subject.sanitizeHifiUrl("  welcome.overte.org/1,2,3  "));
    }

    @Test public void sanitizePreservesExistingSchemesAndEmptyInput() {
        assertEquals("hifi://domain/path", subject.sanitizeHifiUrl("hifi://domain/path"));
        assertEquals("https://example.test/path", subject.sanitizeHifiUrl("https://example.test/path"));
        assertEquals("", subject.sanitizeHifiUrl("  "));
    }

    @Test public void malformedUriIsTrimmedButOtherwisePreserved() {
        assertEquals("bad uri [", subject.sanitizeHifiUrl("  bad uri [  "));
        assertEquals("bad uri [", subject.absoluteHifiAssetUrl("  bad uri [  ", "https://base/"));
    }

    @Test public void relativeAssetUsesSuppliedBaseWithoutChangingAbsoluteUrl() {
        assertEquals("https://base.test/assets/avatar.fst",
                subject.absoluteHifiAssetUrl("/assets/avatar.fst", "https://base.test"));
        assertEquals("atp:/hash", subject.absoluteHifiAssetUrl("atp:/hash", "https://base.test"));
    }

    @Test public void relativeAssetNormalizesExactlyOnePathSeparator() {
        assertEquals("https://base.test/assets/image.png",
                subject.absoluteHifiAssetUrl("assets/image.png", "https://base.test"));
        assertEquals("https://base.test/assets/image.png",
                subject.absoluteHifiAssetUrl("/assets/image.png", "https://base.test/"));
        assertEquals("assets/image.png",
                subject.absoluteHifiAssetUrl("assets/image.png", null));
        assertEquals("assets/image.png",
                subject.absoluteHifiAssetUrl("assets/image.png", "  "));
    }

    @Test public void networkPathAssetsInheritOnlyHttpOrHttpsSchemes() {
        assertEquals("https://cdn.example.test/avatar.png?size=2#image",
                subject.absoluteHifiAssetUrl("//cdn.example.test/avatar.png?size=2#image",
                        "https://base.test/server"));
        assertEquals("http://cdn.example.test/avatar.png",
                subject.absoluteHifiAssetUrl("//cdn.example.test/avatar.png", "http://base.test"));
        assertEquals("//cdn.example.test/avatar.png",
                subject.absoluteHifiAssetUrl("//cdn.example.test/avatar.png", null));
        assertEquals("//cdn.example.test/avatar.png",
                subject.absoluteHifiAssetUrl("//cdn.example.test/avatar.png", "atp:/base"));
        assertEquals("//cdn.example.test/avatar.png",
                subject.absoluteHifiAssetUrl("//cdn.example.test/avatar.png", "bad uri ["));
    }

    @Test public void defaultAssetBaseAndWhitespaceAreDeterministic() {
        assertEquals(HifiUtils.METAVERSE_BASE_URL + "/asset",
                subject.absoluteHifiAssetUrl("  /asset  "));
        assertEquals("", subject.absoluteHifiAssetUrl(" \n\t "));
    }

    @Test public void fixedSeedBareAddressesRetainTheirPayload() {
        Random random = new Random(0x48494649L);
        for (int index = 0; index < 512; ++index) {
            String payload = "domain" + random.nextInt(10_000) + ".test/path/" + index;
            String left = (index & 1) == 0 ? " " : "\t";
            String right = (index & 2) == 0 ? "\n" : "  ";
            assertEquals("hifi://" + payload, subject.sanitizeHifiUrl(left + payload + right));
            assertEquals("https://base/" + payload,
                    subject.absoluteHifiAssetUrl(left + payload + right, "https://base/"));
        }
    }

    @Test public void missingNetworkFieldsFailClosedToEmptyStrings() {
        assertEquals("", subject.sanitizeHifiUrl(null));
        assertEquals("", subject.absoluteHifiAssetUrl(null));
        assertEquals("", subject.absoluteHifiAssetUrl(null, "https://base/"));
    }
}
