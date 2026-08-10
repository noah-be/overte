package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowActivity;
import org.robolectric.shadows.ShadowApplication;

/** Device-free tests for the complete launcher, permission, and recreation flow. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {26, 35}, manifest = Config.NONE)
public final class PermissionsActivityRobolectricTest {
    private static final String WORLD = "hifi://example.com/a%20b";

    @Test
    public void grantedPermissionImmediatelyLaunchesInterfaceAndFinishes() {
        grantMicrophone();
        ActivityController<PermissionsActivity> controller = create(viewIntent("overte://example.com/a%20b"));
        PermissionsActivity activity = controller.get();

        Intent launched = applicationShadow().getNextStartedActivity();
        assertEquals(PhoneInterfaceActivity.class.getName(), launched.getComponent().getClassName());
        assertEquals(WORLD, launched.getStringExtra(PhoneDeepLink.EXTRA_URL));
        assertTrue(activity.isFinishing());
        controller.destroy();
    }

    @Test
    public void deniedPermissionRequestsOnlyMicrophoneAndWaits() {
        ActivityController<PermissionsActivity> controller = create(new Intent(Intent.ACTION_MAIN));
        PermissionsActivity activity = controller.get();

        ShadowActivity.PermissionsRequest request = org.robolectric.Shadows.shadowOf(activity)
                .getLastRequestedPermission();
        assertEquals(PhonePermissionFlow.RECORD_AUDIO_REQUEST, request.requestCode);
        assertEquals(1, request.requestedPermissions.length);
        assertEquals(Manifest.permission.RECORD_AUDIO, request.requestedPermissions[0]);
        assertFalse(activity.isFinishing());
        controller.destroy();
    }

    @Test
    public void denialStillLaunchesBecauseVoiceIsOptional() {
        ActivityController<PermissionsActivity> controller = create(viewIntent("hifi://example.com"));
        PermissionsActivity activity = controller.get();

        activity.onRequestPermissionsResult(PhonePermissionFlow.RECORD_AUDIO_REQUEST,
                new String[] { Manifest.permission.RECORD_AUDIO },
                new int[] { PackageManager.PERMISSION_DENIED });

        assertEquals("hifi://example.com",
                launchedInterfaceIntent().getStringExtra(PhoneDeepLink.EXTRA_URL));
        assertTrue(activity.isFinishing());
        controller.destroy();
    }

    @Test
    public void unrelatedPermissionCallbackDoesNotLaunch() {
        ActivityController<PermissionsActivity> controller = create(new Intent(Intent.ACTION_MAIN));
        PermissionsActivity activity = controller.get();
        // Robolectric models the platform permission dialog as an internal
        // started Activity. It is not an application navigation event.
        applicationShadow().getNextStartedActivity();

        activity.onRequestPermissionsResult(999, new String[0], new int[0]);

        assertNull(applicationShadow().getNextStartedActivity());
        assertFalse(activity.isFinishing());
        controller.destroy();
    }

    @Test
    public void latestIntentWhileDialogIsOpenSupersedesOriginalDestination() {
        ActivityController<PermissionsActivity> controller = create(viewIntent("hifi://old.example"));
        PermissionsActivity activity = controller.get();
        activity.onNewIntent(viewIntent("overte://new.example/path"));

        activity.onRequestPermissionsResult(PhonePermissionFlow.RECORD_AUDIO_REQUEST,
                new String[] { Manifest.permission.RECORD_AUDIO },
                new int[] { PackageManager.PERMISSION_GRANTED });

        assertEquals("hifi://new.example/path",
                launchedInterfaceIntent().getStringExtra(PhoneDeepLink.EXTRA_URL));
        controller.destroy();
    }

    @Test
    public void newerInvalidIntentClearsAnOlderDestination() {
        ActivityController<PermissionsActivity> controller = create(viewIntent("hifi://old.example"));
        PermissionsActivity activity = controller.get();
        activity.onNewIntent(viewIntent("https://not-supported.example"));

        activity.onRequestPermissionsResult(PhonePermissionFlow.RECORD_AUDIO_REQUEST,
                new String[] { Manifest.permission.RECORD_AUDIO }, new int[] { PackageManager.PERMISSION_DENIED });

        assertFalse(launchedInterfaceIntent().hasExtra(PhoneDeepLink.EXTRA_URL));
        controller.destroy();
    }

    @Test
    public void savedStateRecreationPreservesLatestPendingDestinationAndRequestsAgain() {
        ActivityController<PermissionsActivity> first = create(viewIntent("hifi://old.example"));
        first.get().onNewIntent(viewIntent("overte://latest.example"));
        Bundle state = new Bundle();
        first.saveInstanceState(state).pause().stop().destroy();

        ActivityController<PermissionsActivity> recreated = Robolectric
                .buildActivity(PermissionsActivity.class, new Intent(Intent.ACTION_MAIN))
                .create(state).start().resume().visible();
        PermissionsActivity activity = recreated.get();
        ShadowActivity.PermissionsRequest request = org.robolectric.Shadows.shadowOf(activity)
                .getLastRequestedPermission();
        assertEquals(PhonePermissionFlow.RECORD_AUDIO_REQUEST, request.requestCode);

        activity.onRequestPermissionsResult(PhonePermissionFlow.RECORD_AUDIO_REQUEST,
                new String[] { Manifest.permission.RECORD_AUDIO }, new int[] { PackageManager.PERMISSION_DENIED });
        assertEquals("hifi://latest.example",
                launchedInterfaceIntent().getStringExtra(PhoneDeepLink.EXTRA_URL));
        recreated.destroy();
    }

    @Test
    public void savedStateRecreationAfterLaunchDoesNotStartSecondInterface() {
        grantMicrophone();
        ActivityController<PermissionsActivity> first = create(viewIntent("hifi://example.com"));
        assertTrue(first.get().isFinishing());
        assertEquals(PhoneInterfaceActivity.class.getName(),
                applicationShadow().getNextStartedActivity().getComponent().getClassName());
        Bundle state = new Bundle();
        first.saveInstanceState(state).destroy();

        ActivityController<PermissionsActivity> recreated = Robolectric
                .buildActivity(PermissionsActivity.class, viewIntent("hifi://example.com"))
                .create(state).start().resume().visible();

        assertTrue(recreated.get().isFinishing());
        assertNull(applicationShadow().getNextStartedActivity());
        recreated.destroy();
    }

    @Test
    public void repeatedPermissionResultCannotLaunchTwice() {
        ActivityController<PermissionsActivity> controller = create(new Intent(Intent.ACTION_MAIN));
        PermissionsActivity activity = controller.get();
        applicationShadow().getNextStartedActivity();
        activity.onRequestPermissionsResult(PhonePermissionFlow.RECORD_AUDIO_REQUEST,
                new String[0], new int[0]);
        assertEquals(PhoneInterfaceActivity.class.getName(),
                applicationShadow().getNextStartedActivity().getComponent().getClassName());

        activity.onRequestPermissionsResult(PhonePermissionFlow.RECORD_AUDIO_REQUEST,
                new String[0], new int[0]);
        assertNull(applicationShadow().getNextStartedActivity());
        controller.destroy();
    }

    private static ActivityController<PermissionsActivity> create(Intent intent) {
        return Robolectric.buildActivity(PermissionsActivity.class, intent)
                .create().start().resume().visible();
    }

    private static Intent viewIntent(String uri) {
        return new Intent(Intent.ACTION_VIEW, Uri.parse(uri));
    }

    private static void grantMicrophone() {
        applicationShadow().grantPermissions(Manifest.permission.RECORD_AUDIO);
    }

    private static Intent launchedInterfaceIntent() {
        Intent launched = applicationShadow().getNextStartedActivity();
        assertEquals(PhoneInterfaceActivity.class.getName(),
                launched.getComponent().getClassName());
        return launched;
    }

    private static ShadowApplication applicationShadow() {
        return org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication());
    }
}
