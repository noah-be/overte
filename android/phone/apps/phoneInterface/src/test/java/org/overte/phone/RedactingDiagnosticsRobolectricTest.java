package org.overte.phone;

import static org.junit.Assert.*;
import android.Manifest;
import android.content.Intent;
import android.content.Context;
import android.content.ContextWrapper;
import android.content.pm.PackageManager;
import android.util.Log;
import org.junit.Before;
import org.junit.Test;
import org.junit.Rule;
import org.junit.rules.TemporaryFolder;
import org.junit.runner.RunWith;
import org.overte.security.SafeDiagnostics;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowLog;
import java.io.File;
import java.nio.file.Files;

/** Real Phone callers and Android Log boundary; not device retained-output proof. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {26, 35}, manifest = Config.NONE)
public final class RedactingDiagnosticsRobolectricTest {
    @Rule public TemporaryFolder temporary = new TemporaryFolder();
    @Before public void reset() { ShadowLog.clear(); }

    @Test public void restoredOrHistoryLaunchCannotReviveCancelledNavigation() {
        String incoming = "hifi://synthetic.invalid";
        assertEquals(incoming, PhonePendingUrlPolicy.initialDestination(incoming, false, false));
        assertNull(PhonePendingUrlPolicy.initialDestination(incoming, true, false));
        assertNull(PhonePendingUrlPolicy.initialDestination(incoming, false, true));
        assertNull(PhonePendingUrlPolicy.initialDestination(incoming, true, true));
        assertNull(PhonePendingUrlPolicy.initialDestination(null, false, false));
    }

    @Test public void foregroundDeliveryIsLatestOnlyAndBounded() {
        PhoneForegroundDeliveryState state = new PhoneForegroundDeliveryState();
        assertNull(state.pending());
        assertFalse(state.foregroundDelivered());
        state.replace(true);
        assertTrue(state.failedAttempt());
        state.replace(false);
        state.accepted(true); // stale acknowledgement cannot resurrect visibility
        assertEquals(Boolean.FALSE, state.pending());
        assertFalse(state.foregroundDelivered());
        state.accepted(false);
        assertNull(state.pending());
        assertFalse(state.foregroundDelivered());
        state.replace(true);
        for (int attempt = 1; attempt < PhoneForegroundDeliveryState.MAX_ATTEMPTS; attempt++) {
            assertTrue(state.failedAttempt());
        }
        assertFalse(state.failedAttempt());
        assertNull(state.pending());
        assertFalse(state.foregroundDelivered());
        state.accepted(true); // completion after exhausted budget is ignored
        assertFalse(state.foregroundDelivered());
        state.replace(true); // new explicit visibility starts a new delivery budget
        state.accepted(true);
        assertTrue(state.foregroundDelivered());
        assertNull(state.pending());
    }

    private void onlyClosedLogs(int count) {
        int observed = 0;
        for (ShadowLog.LogItem item : ShadowLog.getLogsForTag("OvertePhone")) {
            observed++;
            assertNull(item.throwable);
            assertTrue(item.type == Log.INFO || item.type == Log.WARN);
            assertEquals(SafeDiagnostics.sanitize(item.msg), item.msg);
            assertTrue(item.msg.length() <= 32);
        }
        assertEquals(count, observed);
    }

    @Test public void rawCanariesNeverReachLogcat() {
        String[] canaries = { null, "secret-canary", "OVT_AUTH_READY suffix",
            "OVT_AUTH_READY\u0000", "https://private.invalid/?token=synthetic",
            "token%3Dsynthetic", "Bearer synthetic", "OVT_AUTH_READY\n" };
        for (String input : canaries) { RedactingDiagnostics.warning(input); }
        onlyClosedLogs(canaries.length);
        for (ShadowLog.LogItem item : ShadowLog.getLogsForTag("OvertePhone")) {
            assertEquals("OVT_REDACTED", item.msg);
        }
    }

    @Test public void structuredEventsRemainUseful() {
        for (SafeDiagnostics.Event event : SafeDiagnostics.Event.values()) {
            RedactingDiagnostics.event(event);
        }
        onlyClosedLogs(SafeDiagnostics.Event.values().length);
    }

    @Test public void actualStorageExceptionsLogNoDetails() {
        for (SecureAccountStore.Failure failure : SecureAccountStore.Failure.values()) {
            new SecureAccountStore.StoreException(failure);
        }
        onlyClosedLogs(SecureAccountStore.Failure.values().length);
    }

    @Test public void trustedRootAliasWorksButAccountDirectoryAliasFailsClosed() throws Exception {
        File root = temporary.newFolder("framework-root");
        File alias = new File(temporary.getRoot(), "framework-alias");
        Files.createSymbolicLink(alias.toPath(), root.toPath());
        Context context = new ContextWrapper(RuntimeEnvironment.getApplication()) {
            @Override public Context getApplicationContext() { return this; }
            @Override public File getNoBackupFilesDir() { return alias; }
        };
        SecureAccountStore store = new SecureAccountStore(context);
        assertNull(store.read()); // No keystore operation for an absent record.
        File outside = temporary.newFolder("untrusted-account-target");
        Files.createSymbolicLink(new File(root, "protected-account").toPath(), outside.toPath());
        try {
            store.read();
            fail("account directory link accepted");
        } catch (SecureAccountStore.StoreException expected) {
            assertEquals(SecureAccountStore.Failure.READ, expected.failure);
        } finally {
            Files.delete(new File(root, "protected-account").toPath());
            Files.delete(alias.toPath());
        }
    }

    @Test public void cancelledPermissionCallerEmitsClosedOutcome() {
        ActivityController<PermissionsActivity> controller = Robolectric.buildActivity(
                PermissionsActivity.class, new Intent(Intent.ACTION_MAIN)).create();
        PermissionsActivity activity = controller.get();
        activity.finish();
        ShadowLog.clear();
        activity.onRequestPermissionsResult(PhonePermissionFlow.RECORD_AUDIO_REQUEST,
                new String[] { Manifest.permission.RECORD_AUDIO },
                new int[] { PackageManager.PERMISSION_DENIED });
        onlyClosedLogs(2);
        assertEquals("OVT_CALLBACK_DISCARDED",
                ShadowLog.getLogsForTag("OvertePhone").get(1).msg);
        controller.destroy();
    }
}
