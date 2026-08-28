package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import android.content.Intent;

import org.junit.After;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowApplication;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35, manifest = Config.NONE)
public final class E2eFlightControlActivityTest {
    @After
    public void resetState() {
        PhoneE2eLaunchState.resetForTest();
    }

    @Test
    public void activeSessionRoutesBoundedModeToExistingInterface() {
        PhoneE2eLaunchState.begin();
        PhoneE2eLaunchState.takePendingFlyingOverride();

        launch(PhoneE2eLaunchState.ENABLE_E2E_FLIGHT);

        Intent started = applicationShadow().getNextStartedActivity();
        assertEquals(PhoneInterfaceActivity.class.getName(),
                started.getComponent().getClassName());
        assertEquals(Integer.valueOf(PhoneE2eLaunchState.ENABLE_E2E_FLIGHT),
                PhoneE2eLaunchState.takePendingFlyingOverride());
    }

    @Test
    public void inactiveSessionCannotStartInterface() {
        launch(PhoneE2eLaunchState.ENABLE_E2E_FLIGHT);
        assertNull(applicationShadow().getNextStartedActivity());
        assertNull(PhoneE2eLaunchState.takePendingFlyingOverride());
    }

    @Test
    public void unknownModeFailsClosed() {
        PhoneE2eLaunchState.begin();
        PhoneE2eLaunchState.takePendingFlyingOverride();
        launch(7);
        assertNull(applicationShadow().getNextStartedActivity());
        assertNull(PhoneE2eLaunchState.takePendingFlyingOverride());
    }

    private static void launch(int mode) {
        Intent intent = new Intent(
                RuntimeEnvironment.getApplication(), E2eFlightControlActivity.class);
        intent.putExtra(E2eFlightControlActivity.EXTRA_MODE, mode);
        Robolectric.buildActivity(E2eFlightControlActivity.class, intent)
                .create().start().resume().visible().destroy();
    }

    private static ShadowApplication applicationShadow() {
        return org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication());
    }
}
