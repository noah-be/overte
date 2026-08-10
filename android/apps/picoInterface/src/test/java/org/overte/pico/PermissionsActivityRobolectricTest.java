package org.overte.pico;

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
import org.robolectric.shadows.ShadowActivity;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {26, 35}, manifest = Config.NONE)
public final class PermissionsActivityRobolectricTest {
    @Test public void grantedMicrophoneLaunchesQtWithoutForwardingExternalArguments() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication())
                .grantPermissions(Manifest.permission.RECORD_AUDIO);
        PermissionsActivity activity = create(new Intent().putExtra("args", "--display=OpenXR"));
        Intent launched = nextIntent();
        assertEquals(PicoInterfaceActivity.class.getName(), launched.getComponent().getClassName());
        assertFalse(launched.hasExtra("applicationArguments"));
        assertTrue(activity.isFinishing());
    }

    @Test public void missingMicrophoneRequestsOnlyOptionalAudioPermission() {
        denyMicrophone();
        PermissionsActivity activity = create(new Intent());
        ShadowActivity.PermissionsRequest request = org.robolectric.Shadows.shadowOf(activity)
                .getLastRequestedPermission();
        assertEquals(20, request.requestCode);
        assertArrayEquals(new String[] { Manifest.permission.RECORD_AUDIO }, request.requestedPermissions);
        assertFalse(activity.isFinishing());
    }

    @Test public void denialStillLaunchesButUnrelatedCallbackDoesNot() {
        denyMicrophone();
        PermissionsActivity activity = create(new Intent());
        nextIntent(); // Robolectric permission-dialog activity.
        activity.onRequestPermissionsResult(999, new String[0], new int[0]);
        assertNull(nextIntent());
        activity.onRequestPermissionsResult(20, new String[] { Manifest.permission.RECORD_AUDIO },
                new int[] { PackageManager.PERMISSION_DENIED });
        assertEquals(PicoInterfaceActivity.class.getName(), nextIntent().getComponent().getClassName());
    }

    @Test public void repeatedPermissionCallbackLaunchesExactlyOnce() {
        denyMicrophone();
        PermissionsActivity activity = create(new Intent());
        nextIntent();
        activity.onRequestPermissionsResult(20, new String[0], new int[0]);
        assertNotNull(nextIntent());
        activity.onRequestPermissionsResult(20, new String[0], new int[0]);
        assertNull(nextIntent());
    }

    @Test public void externalArgumentsAreNotForwarded() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication())
                .grantPermissions(Manifest.permission.RECORD_AUDIO);
        create(new Intent().putExtra("args", "--url overte://untrusted.example"));
        assertFalse(nextIntent().hasExtra("applicationArguments"));
    }

    @Test public void restoredLaunchedStateDoesNotLaunchAgain() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication())
                .grantPermissions(Manifest.permission.RECORD_AUDIO);
        ActivityController<PermissionsActivity> original = Robolectric.buildActivity(
                PermissionsActivity.class, new Intent()).create().start().resume();
        assertNotNull(nextIntent());
        Bundle state = new Bundle();
        original.saveInstanceState(state).pause().stop().destroy();
        PermissionsActivity restored = Robolectric.buildActivity(
                PermissionsActivity.class, new Intent()).create(state).start().resume().get();
        assertNull(nextIntent());
        assertTrue(restored.isFinishing());
    }

    private static PermissionsActivity create(Intent intent) {
        return Robolectric.buildActivity(PermissionsActivity.class, intent).create().start().resume().get();
    }
    private static void denyMicrophone() {
        org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication())
                .denyPermissions(Manifest.permission.RECORD_AUDIO);
    }
    private static Intent nextIntent() {
        return org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication()).getNextStartedActivity();
    }
}
