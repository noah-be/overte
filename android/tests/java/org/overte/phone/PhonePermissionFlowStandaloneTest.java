package org.overte.phone;

/** Dependency-free regression test for optional voice permission routing. */
public final class PhonePermissionFlowStandaloneTest {
    public static void main(String[] arguments) {
        if (!PhonePermissionFlow.shouldLaunchInterfaceAfterResult(
                PhonePermissionFlow.RECORD_AUDIO_REQUEST)) {
            throw new AssertionError("microphone result must continue into Interface");
        }
        int[] unrelated = { Integer.MIN_VALUE, -1, 0, 19, 21, Integer.MAX_VALUE };
        for (int requestCode : unrelated) {
            if (PhonePermissionFlow.shouldLaunchInterfaceAfterResult(requestCode)) {
                throw new AssertionError("unrelated request accepted: " + requestCode);
            }
        }
        System.out.println("PhonePermissionFlowStandaloneTest: 7 assertions passed");
    }
}
