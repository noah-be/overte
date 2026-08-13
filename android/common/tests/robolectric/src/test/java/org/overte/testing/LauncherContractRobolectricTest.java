package org.overte.testing;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;

import java.io.File;
import java.util.Arrays;
import java.util.Collection;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.ParameterizedRobolectricTestRunner;
import org.robolectric.Robolectric;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowActivity;
import org.robolectric.shadows.ShadowApplication;

/** Shared lifecycle contract for every maintained Android Interface launcher. */
@RunWith(ParameterizedRobolectricTestRunner.class)
@Config(sdk = {26}, manifest = Config.NONE)
public final class LauncherContractRobolectricTest {
    private static final String[] MICROPHONE = {Manifest.permission.RECORD_AUDIO};
    private static final String[] LEGACY_PERMISSIONS = {
            Manifest.permission.READ_EXTERNAL_STORAGE,
            Manifest.permission.WRITE_EXTERNAL_STORAGE,
            Manifest.permission.RECORD_AUDIO,
    };

    private final ContractCase contract;

    public LauncherContractRobolectricTest(ContractCase contract) {
        this.contract = contract;
    }

    @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
    public static Collection<Object[]> launchers() {
        return Arrays.asList(new Object[][] {
                {new ContractCase("Phone", org.overte.phone.PermissionsActivity.class,
                        org.overte.phone.PhoneInterfaceActivity.class, MICROPHONE)},
                {new ContractCase("Pico", org.overte.pico.PermissionsActivity.class,
                        org.overte.pico.PicoInterfaceActivity.class, MICROPHONE)},
                {new ContractCase("Quest", io.highfidelity.questInterface.PermissionsChecker.class,
                        io.highfidelity.questInterface.InterfaceActivity.class, LEGACY_PERMISSIONS)},
                {new ContractCase("legacy Interface", HostPermissionChecker.class,
                        io.highfidelity.hifiinterface.InterfaceActivity.class, LEGACY_PERMISSIONS)},
        });
    }

    @Test
    public void grantedPermissionsLaunchExactlyOneInterfaceAndFinish() {
        application().grantPermissions(contract.permissions);
        ActivityController<? extends Activity> controller = create(new Intent());
        assertTarget(application().getNextStartedActivity());
        assertTrue(controller.get().isFinishing());
        assertNull(application().getNextStartedActivity());
        controller.destroy();
    }

    @Test
    public void missingPermissionsRequestTheReviewedSet() {
        application().denyPermissions(contract.permissions);
        ActivityController<? extends Activity> controller = create(new Intent());
        ShadowActivity.PermissionsRequest request = org.robolectric.Shadows
                .shadowOf(controller.get()).getLastRequestedPermission();
        assertNotNull(request);
        assertEquals(20, request.requestCode);
        assertArrayEquals(contract.permissions, request.requestedPermissions);
        controller.destroy();
    }

    @Test
    public void onlyTheReviewedPermissionCallbackMayLaunch() {
        application().denyPermissions(contract.permissions);
        ActivityController<? extends Activity> controller = create(new Intent());
        application().getNextStartedActivity(); // Robolectric's permission-dialog Activity.
        controller.get().onRequestPermissionsResult(
                999, contract.permissions, new int[] {PackageManager.PERMISSION_DENIED});
        assertNull(application().getNextStartedActivity());
        controller.get().onRequestPermissionsResult(
                20, contract.permissions, new int[] {PackageManager.PERMISSION_DENIED});
        assertTarget(application().getNextStartedActivity());
        controller.destroy();
    }

    @Test
    public void restoredLaunchedStateNeverStartsASecondInterface() {
        application().grantPermissions(contract.permissions);
        ActivityController<? extends Activity> first = create(new Intent());
        assertTarget(application().getNextStartedActivity());
        Bundle state = new Bundle();
        first.saveInstanceState(state).pause().stop().destroy();

        ActivityController<? extends Activity> restored = Robolectric
                .buildActivity(contract.launcher, new Intent()).create(state).start().resume();
        assertTrue(restored.get().isFinishing());
        assertNull(application().getNextStartedActivity());
        restored.destroy();
    }

    private ActivityController<? extends Activity> create(Intent intent) {
        return Robolectric.buildActivity(contract.launcher, intent).create().start().resume();
    }

    private void assertTarget(Intent launched) {
        assertNotNull(launched);
        assertEquals(contract.target.getName(), launched.getComponent().getClassName());
    }

    private static ShadowApplication application() {
        return org.robolectric.Shadows.shadowOf(RuntimeEnvironment.getApplication());
    }

    private static final class ContractCase {
        final String name;
        final Class<? extends Activity> launcher;
        final Class<?> target;
        final String[] permissions;

        ContractCase(String name, Class<? extends Activity> launcher,
                Class<?> target, String[] permissions) {
            this.name = name;
            this.launcher = launcher;
            this.target = target;
            this.permissions = permissions;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    /** Supplies the host-safe OBB lookup required by the legacy launcher. */
    public static final class HostPermissionChecker
            extends io.highfidelity.hifiinterface.PermissionChecker {
        @Override
        public File getObbDir() {
            return new File(RuntimeEnvironment.getApplication().getCacheDir(), "legacy-interface-obb");
        }
    }
}
