package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import android.content.Intent;
import android.net.Uri;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;

/** Android-boundary tests for exported and internal deep-link intent parsing. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {26, 35}, manifest = Config.NONE)
public final class PhoneDeepLinkRobolectricTest {
    @Test
    public void exportedViewIntentCanonicalizesSupportedSchemes() {
        assertEquals("hifi://example.com/a%20b?x=%09",
                PhoneDeepLink.fromIntent(new Intent(Intent.ACTION_VIEW,
                        Uri.parse("OvErTe://example.com/a%20b?x=%09"))));
        assertEquals("hifi:/1,2,3",
                PhoneDeepLink.fromIntent(new Intent(Intent.ACTION_VIEW, Uri.parse("HIFI:/1,2,3"))));
    }

    @Test
    public void exportedBoundaryRejectsNullWrongActionsAndUnsupportedDestinations() {
        assertNull(PhoneDeepLink.fromIntent(null));
        assertNull(PhoneDeepLink.fromIntent(new Intent(Intent.ACTION_MAIN,
                Uri.parse("hifi://example.com"))));
        assertNull(PhoneDeepLink.fromIntent(new Intent(Intent.ACTION_VIEW)));
        assertNull(PhoneDeepLink.fromIntent(new Intent(Intent.ACTION_VIEW,
                Uri.parse("https://example.com"))));
    }

    @Test
    public void internalExtraIsValidatedWithTheSameBoundaryRules() {
        Intent valid = new Intent().putExtra(PhoneDeepLink.EXTRA_URL, "overte://example.com/path");
        assertEquals("hifi://example.com/path", PhoneDeepLink.fromInternalExtra(valid));

        assertNull(PhoneDeepLink.fromInternalExtra(null));
        assertNull(PhoneDeepLink.fromInternalExtra(new Intent()));
        assertNull(PhoneDeepLink.fromInternalExtra(
                new Intent().putExtra(PhoneDeepLink.EXTRA_URL, "file:///data/local/tmp/payload")));
        assertNull(PhoneDeepLink.fromInternalExtra(
                new Intent().putExtra(PhoneDeepLink.EXTRA_URL, "hifi://host/raw space")));
    }

    @Test
    public void directUriNormalizationHandlesMissingValues() {
        assertNull(PhoneDeepLink.normalize(null));
        assertEquals("hifi://host/%F0%9F%8C%8D",
                PhoneDeepLink.normalize(Uri.parse("overte://host/%F0%9F%8C%8D")));
    }
}
