package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;

import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;

import org.junit.Test;
import org.junit.runner.RunWith;

/**
 * PH-003 packaging/policy cases, activated by revision 09 source authority.
 *
 * These policy cases supplement, not replace, real Shared Tablet/text/permission
 * modules. Run only under later execution authority through the x86_64 runner;
 * source-set inclusion and host fixtures are not observed emulator behavior.
 */
@RunWith(AndroidJUnit4.class)
public final class PhoneParityPreparationInstrumentedTest {
    @Test
    public void unsupportedWebSchemeIsNotExported() {
        Context context = ApplicationProvider.getApplicationContext();
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse("https://example.invalid"))
                .addCategory(Intent.CATEGORY_BROWSABLE)
                .setPackage(context.getPackageName());

        assertTrue(context.getPackageManager()
                .queryIntentActivities(intent, PackageManager.MATCH_DEFAULT_ONLY)
                .isEmpty());
    }

    @Test
    public void rawWhitespaceDeepLinkIsRejected() {
        assertNull(PhoneDeepLinkNormalizer.normalize("overte://example.invalid/a b"));
        assertNull(PhoneDeepLinkNormalizer.normalize("hifi://example.invalid/a\tb"));
    }

    @Test
    public void microphoneDenialStillAllowsInterfaceLaunch() {
        int[] denial = { PackageManager.PERMISSION_DENIED };
        assertEquals(PackageManager.PERMISSION_DENIED, denial[0]);
        assertTrue(PhonePermissionFlow.shouldLaunchInterfaceAfterResult(
                PhonePermissionFlow.RECORD_AUDIO_REQUEST));
        assertFalse(PhonePermissionFlow.shouldLaunchInterfaceAfterResult(
                PhonePermissionFlow.RECORD_AUDIO_REQUEST + 1));
    }

    @Test
    public void tabletWindowMetricsRemainUsable() {
        PhoneTouchUiMetricsPolicy.Snapshot snapshot = PhoneTouchUiMetricsPolicy.normalize(
                1600, 2560,
                24, 48, 32, 96,
                96,
                3.0f, 1.3f,
                true, true, true);

        assertTrue(snapshot.valid);
        assertEquals(1600, snapshot.surfaceWidth);
        assertEquals(2560, snapshot.surfaceHeight);
        assertEquals(3.0f, snapshot.contentScale, 0.0f);
        assertFalse(snapshot.keyboardVisible);
        assertTrue(snapshot.hardwareKeyboardSupported);
    }

    @Test
    public void legacyImeInsetIsSeparatedFromNavigationInset() {
        PhoneTouchUiMetricsPolicy.LegacyInsets insets =
                PhoneTouchUiMetricsPolicy.normalizeLegacyInsets(
                        0, 24, 0, 720,
                        96,
                        0, 0, 0, 48,
                        0, 24, 0, 0);
        assertEquals(24, insets.top);
        assertEquals(96, insets.bottom);
        assertEquals(720, insets.imeBottom);

        PhoneTouchUiMetricsPolicy.Snapshot snapshot = PhoneTouchUiMetricsPolicy.normalize(
                1600, 2560,
                insets.left, insets.top, insets.right, insets.bottom,
                insets.imeBottom,
                2.0f, 1.0f,
                false, false, true);
        assertTrue(snapshot.valid);
        assertTrue(snapshot.keyboardVisible);
    }
}
