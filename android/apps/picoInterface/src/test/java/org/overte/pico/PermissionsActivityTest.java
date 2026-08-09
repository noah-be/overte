package org.overte.pico;

import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;

@RunWith(RobolectricTestRunner.class)
public class PermissionsActivityTest {
    @Test
    public void grantedMicrophoneLaunchesInterfaceImmediately() {
        PermissionsActivity activity = Robolectric.buildActivity(PermissionsActivity.class).get();
        shadowOf(activity).grantPermissions(Manifest.permission.RECORD_AUDIO);
        activity.onCreate(null);
        Intent started = shadowOf(activity).getNextStartedActivity();
        assertEquals(PicoInterfaceActivity.class.getName(), started.getComponent().getClassName());
        assertTrue(activity.isFinishing());
    }

    @Test
    public void denialStillLaunchesBecauseVoiceIsOptional() {
        PermissionsActivity activity = Robolectric.buildActivity(PermissionsActivity.class).create().get();
        activity.onRequestPermissionsResult(20,
            new String[] { Manifest.permission.RECORD_AUDIO },
            new int[] { PackageManager.PERMISSION_DENIED });
        assertNotNull(shadowOf(activity).getNextStartedActivity());
        assertTrue(activity.isFinishing());
    }

    @Test
    public void restoredLaunchedStatePreventsDuplicateIntent() {
        Bundle state = new Bundle();
        state.putBoolean("interfaceLaunched", true);
        PermissionsActivity activity = Robolectric.buildActivity(PermissionsActivity.class).get();
        activity.onCreate(state);
        assertNull(shadowOf(activity).getNextStartedActivity());
        assertTrue(activity.isFinishing());
    }
}
