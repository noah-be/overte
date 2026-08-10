package io.highfidelity.hifiinterface;

import static org.junit.Assert.*;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;

import java.io.File;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 26}, manifest = Config.NONE)
public final class PermissionCheckerRobolectricTest {
    private static final String[] REQUIRED = { Manifest.permission.READ_EXTERNAL_STORAGE,
            Manifest.permission.WRITE_EXTERNAL_STORAGE, Manifest.permission.RECORD_AUDIO };

    @Test public void allGrantedLaunchesInterfaceAndTransfersArguments() {
        grantAll();
        String arguments = "--url \"hifi://welcome/path?a=1&b=2\"\n--display=legacy";
        PermissionChecker activity = create(new Intent().putExtra("args", arguments));
        Intent launched = nextIntent();
        assertEquals(InterfaceActivity.class.getName(), launched.getComponent().getClassName());
        assertEquals(arguments, launched.getStringExtra("args"));
        assertTrue(activity.isFinishing());
    }

    @Test public void missingPermissionsRequestsCompleteLegacySet() {
        denyAll();
        PermissionChecker activity = create(new Intent());
        org.robolectric.shadows.ShadowActivity.PermissionsRequest request =
                org.robolectric.Shadows.shadowOf(activity).getLastRequestedPermission();
        assertEquals(20, request.requestCode);
        assertArrayEquals(REQUIRED, request.requestedPermissions);
    }

    @Test public void denialOrInterruptedResultLaunchesButUnrelatedCallbackDoesNot() {
        denyAll();
        PermissionChecker activity = create(new Intent());
        nextIntent();
        activity.onRequestPermissionsResult(999, REQUIRED, new int[] { PackageManager.PERMISSION_DENIED });
        assertNull(nextIntent());
        activity.onRequestPermissionsResult(20, new String[0], new int[0]);
        assertEquals(InterfaceActivity.class.getName(), nextIntent().getComponent().getClassName());
    }

    @Test public void repeatedPermissionCallbackLaunchesExactlyOnce() {
        denyAll();
        PermissionChecker activity = create(new Intent());
        nextIntent();
        activity.onRequestPermissionsResult(20, REQUIRED, new int[] { PackageManager.PERMISSION_DENIED });
        assertNotNull(nextIntent());
        activity.onRequestPermissionsResult(20, REQUIRED, new int[] { PackageManager.PERMISSION_GRANTED });
        assertNull(nextIntent());
    }

    @Test public void launchedSavedStateDoesNotStartInterfaceAgain() {
        grantAll();
        ActivityController<HostPermissionChecker> original = Robolectric.buildActivity(
                HostPermissionChecker.class, new Intent()).create().start().resume();
        assertNotNull(nextIntent());
        Bundle state = new Bundle();
        original.saveInstanceState(state).pause().stop().destroy();
        PermissionChecker restored = Robolectric.buildActivity(
                HostPermissionChecker.class, new Intent()).create(state).start().resume().get();
        assertNull(nextIntent());
        assertTrue(restored.isFinishing());
    }

    @Test public void creationStartsCrashUploaderService() {
        denyAll();
        create(new Intent());
        Intent service = org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication())
                .getNextStartedService();
        assertEquals(BreakpadUploaderService.class.getName(), service.getComponent().getClassName());
    }

    private static PermissionChecker create(Intent intent) {
        return Robolectric.buildActivity(HostPermissionChecker.class, intent).create().start().resume().get();
    }
    private static void grantAll() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).grantPermissions(REQUIRED);
    }
    private static void denyAll() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).denyPermissions(REQUIRED);
    }
    private static Intent nextIntent() {
        return org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).getNextStartedActivity();
    }

    /** Replaces only Android's external-volume lookup, unavailable with Config.NONE. */
    public static final class HostPermissionChecker extends PermissionChecker {
        @Override public File getObbDir() {
            return new File(RuntimeEnvironment.getApplication().getCacheDir(), "legacy-interface-obb");
        }
    }
}
