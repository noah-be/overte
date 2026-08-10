package org.overte.pico;

/** Host-side tests for Pico launch arguments and restart-alarm selection. */
public final class PicoInterfaceActivityPolicyStandaloneTest {
    private static int assertions;

    public static void main(String[] arguments) {
        applicationArgumentsAreComposedWithoutAndroid();
        exactAlarmChoiceMatchesAndroidPolicyBoundary();
        lifecycleOwnershipRejectsStaleActivities();
        System.out.println("PicoInterfaceActivityPolicyStandaloneTest: "
                + assertions + " assertions passed");
    }

    private static void applicationArgumentsAreComposedWithoutAndroid() {
        equal("--display=OpenXR --cache /cache",
                PicoInterfaceActivityPolicy.applicationParameters(false, null, "/cache"));
        equal("--url hifi://example --cache /cache dir",
                PicoInterfaceActivityPolicy.applicationParameters(
                        true, "--url hifi://example", "/cache dir"));
        equal(" --cache /cache",
                PicoInterfaceActivityPolicy.applicationParameters(true, "", "/cache"));
        equal("--display=OpenXR --cache /cache",
                PicoInterfaceActivityPolicy.applicationParameters(true, null, "/cache"));
    }

    private static void exactAlarmChoiceMatchesAndroidPolicyBoundary() {
        check(PicoInterfaceActivityPolicy.canUseExactRestart(23, false));
        check(PicoInterfaceActivityPolicy.canUseExactRestart(30, false));
        check(PicoInterfaceActivityPolicy.canUseExactRestart(31, true));
        check(PicoInterfaceActivityPolicy.canUseExactRestart(35, true));
        check(!PicoInterfaceActivityPolicy.canUseExactRestart(31, false));
        check(!PicoInterfaceActivityPolicy.canUseExactRestart(35, false));
    }

    private static void lifecycleOwnershipRejectsStaleActivities() {
        PicoActivityInstancePolicy<Object> instances = new PicoActivityInstancePolicy<>();
        Object first = new Object();
        Object replacement = new Object();
        same(null, instances.current());
        instances.register(first);
        same(first, instances.current());
        instances.register(replacement);
        instances.clear(first);
        same(replacement, instances.current());
        instances.clear(replacement);
        same(null, instances.current());
    }

    private static void equal(String expected, String actual) {
        ++assertions;
        if (!expected.equals(actual)) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }

    private static void check(boolean condition) {
        ++assertions;
        if (!condition) {
            throw new AssertionError("condition was false");
        }
    }


    private static void same(Object expected, Object actual) {
        ++assertions;
        if (expected != actual) {
            throw new AssertionError("expected identical instances");
        }
    }
}
