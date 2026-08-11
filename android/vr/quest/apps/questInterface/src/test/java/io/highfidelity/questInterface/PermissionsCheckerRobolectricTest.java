package io.highfidelity.questInterface;

import static org.junit.Assert.*;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 35}, manifest = Config.NONE)
public final class PermissionsCheckerRobolectricTest {
    private static final String[] REQUIRED = { Manifest.permission.READ_EXTERNAL_STORAGE,
            Manifest.permission.WRITE_EXTERNAL_STORAGE, Manifest.permission.RECORD_AUDIO };

    @Test public void allGrantedLaunchesQuestAndTransfersArguments() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).grantPermissions(REQUIRED);
        PermissionsChecker activity = create(new Intent().putExtra("args", "--url hifi://safe"));
        Intent launched = nextIntent();
        assertEquals(InterfaceActivity.class.getName(), launched.getComponent().getClassName());
        assertEquals("--url hifi://safe", launched.getStringExtra("applicationArguments"));
        assertTrue(activity.isFinishing());
    }

    @Test public void missingPermissionsRequestsTheCompleteReviewedSet() {
        denyRequiredPermissions();
        PermissionsChecker activity = create(new Intent());
        org.robolectric.shadows.ShadowActivity.PermissionsRequest request =
                org.robolectric.Shadows.shadowOf(activity).getLastRequestedPermission();
        assertEquals(20, request.requestCode);
        assertArrayEquals(REQUIRED, request.requestedPermissions);
    }

    @Test public void denialLaunchesButUnrelatedCallbackDoesNot() {
        denyRequiredPermissions();
        PermissionsChecker activity = create(new Intent());
        nextIntent();
        activity.onRequestPermissionsResult(999, REQUIRED,
                new int[] { PackageManager.PERMISSION_DENIED });
        assertNull(nextIntent());
        activity.onRequestPermissionsResult(20, REQUIRED,
                new int[] { PackageManager.PERMISSION_DENIED });
        assertEquals(InterfaceActivity.class.getName(), nextIntent().getComponent().getClassName());
    }

    @Test public void repeatedPermissionCallbackLaunchesExactlyOnce() {
        denyRequiredPermissions();
        PermissionsChecker activity = create(new Intent());
        nextIntent();
        activity.onRequestPermissionsResult(20, REQUIRED, new int[] { PackageManager.PERMISSION_DENIED });
        assertNotNull(nextIntent());
        activity.onRequestPermissionsResult(20, REQUIRED, new int[] { PackageManager.PERMISSION_GRANTED });
        assertNull(nextIntent());
    }

    @Test public void interruptedEmptyPermissionResultStillLaunches() {
        PermissionsChecker activity = create(new Intent());
        nextIntent();
        activity.onRequestPermissionsResult(20, new String[0], new int[0]);
        assertEquals(InterfaceActivity.class.getName(), nextIntent().getComponent().getClassName());
    }

    @Test public void emptyArgumentsAreNotForwarded() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).grantPermissions(REQUIRED);
        create(new Intent().putExtra("args", ""));
        assertFalse(nextIntent().hasExtra("applicationArguments"));
    }

    @Test public void restoredLaunchedStateDoesNotLaunchAgain() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).grantPermissions(REQUIRED);
        ActivityController<PermissionsChecker> original = Robolectric.buildActivity(
                PermissionsChecker.class, new Intent()).create().start().resume();
        assertNotNull(nextIntent());
        Bundle state = new Bundle();
        original.saveInstanceState(state).pause().stop().destroy();
        PermissionsChecker restored = Robolectric.buildActivity(
                PermissionsChecker.class, new Intent()).create(state).start().resume().get();
        assertNull(nextIntent());
        assertTrue(restored.isFinishing());
    }

    private static PermissionsChecker create(Intent intent) {
        return Robolectric.buildActivity(PermissionsChecker.class, intent).create().start().resume().get();
    }
    private static void denyRequiredPermissions() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).denyPermissions(REQUIRED);
    }
    private static Intent nextIntent() {
        return org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).getNextStartedActivity();
    }
}
