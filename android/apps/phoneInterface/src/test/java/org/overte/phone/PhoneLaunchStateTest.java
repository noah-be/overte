package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class PhoneLaunchStateTest {
    @Test
    public void restoredExternalUrlIsValidated() {
        PhoneLaunchState valid = new PhoneLaunchState("overte://example.com", false);
        PhoneLaunchState unsafe = new PhoneLaunchState("overte://example.com/a b", false);

        assertEquals("hifi://example.com", valid.pendingUrl());
        assertNull(unsafe.pendingUrl());
    }

    @Test
    public void newerIntentReplacesOrClearsPendingUrl() {
        PhoneLaunchState state = new PhoneLaunchState("overte://first", false);
        state.replacePendingUrl("hifi://second");
        assertEquals("hifi://second", state.pendingUrl());

        state.replacePendingUrl("https://unsupported");
        assertNull(state.pendingUrl());
    }

    @Test
    public void interfaceLaunchCanBeginExactlyOnce() {
        PhoneLaunchState state = new PhoneLaunchState(null, false);
        assertTrue(state.beginInterfaceLaunch());
        assertTrue(state.interfaceLaunched());
        assertFalse(state.beginInterfaceLaunch());
    }

    @Test
    public void restoredLaunchPreventsDuplicateNativeActivity() {
        PhoneLaunchState state = new PhoneLaunchState("overte://pending", true);
        assertFalse(state.beginInterfaceLaunch());
        assertEquals("hifi://pending", state.pendingUrl());
    }

    @Test
    public void pendingUrlMayChangeAfterLaunchWithoutResettingGuard() {
        PhoneLaunchState state = new PhoneLaunchState("overte://first", false);
        assertTrue(state.beginInterfaceLaunch());
        state.replacePendingUrl("overte://newer");
        assertEquals("hifi://newer", state.pendingUrl());
        assertFalse(state.beginInterfaceLaunch());
    }

    @Test
    public void nullReplacementExplicitlyClearsPendingUrl() {
        PhoneLaunchState state = new PhoneLaunchState("hifi://first", false);
        state.replacePendingUrl(null);
        assertNull(state.pendingUrl());
        assertFalse(state.interfaceLaunched());
    }
}
