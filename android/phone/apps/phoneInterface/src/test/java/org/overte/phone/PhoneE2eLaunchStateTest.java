package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.After;
import org.junit.Test;

public class PhoneE2eLaunchStateTest {
    @After
    public void resetState() {
        PhoneE2eLaunchState.resetForTest();
    }

    @Test
    public void sessionStartsWithGroundPreparationAndEnablesFlightOnce() {
        PhoneE2eLaunchState.begin();
        assertTrue(PhoneE2eLaunchState.isActive());
        assertEquals(Integer.valueOf(PhoneE2eLaunchState.PREPARE_GROUNDED_FIXTURE),
                PhoneE2eLaunchState.takePendingFlyingOverride());
        assertNull(PhoneE2eLaunchState.takePendingFlyingOverride());

        assertTrue(PhoneE2eLaunchState.requestFlyingOverride(
                PhoneE2eLaunchState.ENABLE_E2E_FLIGHT));
        assertEquals(Integer.valueOf(PhoneE2eLaunchState.ENABLE_E2E_FLIGHT),
                PhoneE2eLaunchState.takePendingFlyingOverride());
    }

    @Test
    public void restoreClosesSessionAndRejectsFurtherCommands() {
        PhoneE2eLaunchState.begin();
        PhoneE2eLaunchState.takePendingFlyingOverride();
        assertTrue(PhoneE2eLaunchState.requestFlyingOverride(
                PhoneE2eLaunchState.RESTORE_STORED_PREFERENCE));
        assertEquals(Integer.valueOf(PhoneE2eLaunchState.RESTORE_STORED_PREFERENCE),
                PhoneE2eLaunchState.takePendingFlyingOverride());
        PhoneE2eLaunchState.finishRestore();
        assertFalse(PhoneE2eLaunchState.isActive());
        assertFalse(PhoneE2eLaunchState.requestFlyingOverride(
                PhoneE2eLaunchState.ENABLE_E2E_FLIGHT));
        assertNull(PhoneE2eLaunchState.takePendingFlyingOverride());
    }

    @Test
    public void invalidModesFailClosed() {
        PhoneE2eLaunchState.begin();
        assertFalse(PhoneE2eLaunchState.requestFlyingOverride(-2));
        assertFalse(PhoneE2eLaunchState.requestFlyingOverride(2));
        assertEquals(Integer.valueOf(PhoneE2eLaunchState.PREPARE_GROUNDED_FIXTURE),
                PhoneE2eLaunchState.takePendingFlyingOverride());
    }
}
