package org.overte.phone;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class PhonePermissionFlowTest {
    @Test
    public void microphoneResultContinuesForGrantOrDenial() {
        assertTrue(PhonePermissionFlow.shouldLaunchInterfaceAfterResult(
                PhonePermissionFlow.RECORD_AUDIO_REQUEST));
    }

    @Test
    public void unrelatedPermissionCallbacksAreIgnored() {
        assertFalse(PhonePermissionFlow.shouldLaunchInterfaceAfterResult(-1));
        assertFalse(PhonePermissionFlow.shouldLaunchInterfaceAfterResult(0));
        assertFalse(PhonePermissionFlow.shouldLaunchInterfaceAfterResult(19));
        assertFalse(PhonePermissionFlow.shouldLaunchInterfaceAfterResult(21));
        assertFalse(PhonePermissionFlow.shouldLaunchInterfaceAfterResult(Integer.MAX_VALUE));
    }
}
