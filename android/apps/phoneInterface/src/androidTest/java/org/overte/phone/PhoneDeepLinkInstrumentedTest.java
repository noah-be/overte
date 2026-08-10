package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import android.content.Intent;
import android.net.Uri;

import androidx.test.ext.junit.runners.AndroidJUnit4;

import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public final class PhoneDeepLinkInstrumentedTest {
    @Test
    public void exportedViewIntentIsCanonicalized() {
        Intent intent = new Intent(Intent.ACTION_VIEW,
                Uri.parse("overte://example.com/place%20name"));
        assertEquals("hifi://example.com/place%20name", PhoneDeepLink.fromIntent(intent));
    }

    @Test
    public void nonViewAndUnsafeIntentsAreRejected() {
        assertNull(PhoneDeepLink.fromIntent(new Intent(Intent.ACTION_MAIN)));
        assertNull(PhoneDeepLink.fromIntent(new Intent(Intent.ACTION_VIEW,
                Uri.parse("https://example.com"))));
    }

    @Test
    public void internalExtraIsValidatedAgain() {
        Intent valid = new Intent().putExtra(PhoneDeepLink.EXTRA_URL, "overte://localhost");
        Intent invalid = new Intent().putExtra(PhoneDeepLink.EXTRA_URL, "overte://bad path");
        assertEquals("hifi://localhost", PhoneDeepLink.fromInternalExtra(valid));
        assertNull(PhoneDeepLink.fromInternalExtra(invalid));
    }

    @Test
    public void nullIntentDataAndMissingInternalExtraAreRejected() {
        assertNull(PhoneDeepLink.fromIntent(null));
        assertNull(PhoneDeepLink.fromIntent(new Intent(Intent.ACTION_VIEW)));
        assertNull(PhoneDeepLink.fromInternalExtra(null));
        assertNull(PhoneDeepLink.fromInternalExtra(new Intent()));
    }

    @Test
    public void wrongActionCannotSmuggleValidDeepLinkData() {
        Intent intent = new Intent(Intent.ACTION_SEND, Uri.parse("overte://localhost"));
        assertNull(PhoneDeepLink.fromIntent(intent));
    }
}
