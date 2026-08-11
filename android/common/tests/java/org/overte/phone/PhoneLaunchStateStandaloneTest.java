package org.overte.phone;

/** Dependency-free host contract for the launcher state machine. */
public final class PhoneLaunchStateStandaloneTest {
    private static int assertions;

    public static void main(String[] arguments) {
        validatesRestoredUrl();
        replacesPendingIntent();
        launchesExactlyOnce();
        restoresAlreadyLaunchedState();
        System.out.println("PhoneLaunchStateStandaloneTest: " + assertions
                + " assertions passed");
    }

    private static void validatesRestoredUrl() {
        PhoneLaunchState valid = new PhoneLaunchState("overte://example.com", false);
        PhoneLaunchState unsafe = new PhoneLaunchState("overte://bad path", false);
        expectEquals("hifi://example.com", valid.pendingUrl());
        expectEquals(null, unsafe.pendingUrl());
    }

    private static void replacesPendingIntent() {
        PhoneLaunchState state = new PhoneLaunchState("overte://first", false);
        state.replacePendingUrl("hifi://second");
        expectEquals("hifi://second", state.pendingUrl());
        state.replacePendingUrl("https://unsupported");
        expectEquals(null, state.pendingUrl());
    }

    private static void launchesExactlyOnce() {
        PhoneLaunchState state = new PhoneLaunchState(null, false);
        expectTrue(state.beginInterfaceLaunch());
        expectTrue(state.interfaceLaunched());
        expectFalse(state.beginInterfaceLaunch());
    }

    private static void restoresAlreadyLaunchedState() {
        PhoneLaunchState state = new PhoneLaunchState("overte://pending", true);
        expectFalse(state.beginInterfaceLaunch());
        expectEquals("hifi://pending", state.pendingUrl());
    }

    private static void expectTrue(boolean actual) {
        ++assertions;
        if (!actual) {
            throw new AssertionError("expected true");
        }
    }

    private static void expectFalse(boolean actual) {
        ++assertions;
        if (actual) {
            throw new AssertionError("expected false");
        }
    }

    private static void expectEquals(String expected, String actual) {
        ++assertions;
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }
}
