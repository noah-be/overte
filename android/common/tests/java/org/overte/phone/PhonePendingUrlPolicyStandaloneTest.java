package org.overte.phone;

/** Dependency-free host checks for pending URL lifecycle and retry policy. */
public final class PhonePendingUrlPolicyStandaloneTest {
    private static int assertions;

    private PhonePendingUrlPolicyStandaloneTest() {
    }

    public static void main(String[] args) {
        for (boolean restored : new boolean[] { false, true }) {
            for (boolean fromHistory : new boolean[] { false, true }) {
                String destination = PhonePendingUrlPolicy.initialDestination(
                        "hifi://explicit-navigation", restored, fromHistory);
                check(restored || fromHistory
                        ? destination == null
                        : "hifi://explicit-navigation".equals(destination));
                check(PhonePendingUrlPolicy.initialDestination(
                        null, restored, fromHistory) == null);
            }
        }

        check(!PhonePendingUrlPolicy.canAttempt(null, false));
        check(!PhonePendingUrlPolicy.canAttempt(null, true));
        check(!PhonePendingUrlPolicy.canAttempt("hifi://pending", false));
        check(PhonePendingUrlPolicy.canAttempt("hifi://pending", true));

        check(PhonePendingUrlPolicy.afterFailedAttempt(true, 1, 300)
                == PhonePendingUrlPolicy.FailedAttemptAction.RETRY);
        check(PhonePendingUrlPolicy.afterFailedAttempt(true, 299, 300)
                == PhonePendingUrlPolicy.FailedAttemptAction.RETRY);
        check(PhonePendingUrlPolicy.afterFailedAttempt(true, 300, 300)
                == PhonePendingUrlPolicy.FailedAttemptAction.DROP);
        check(PhonePendingUrlPolicy.afterFailedAttempt(false, 1, 300)
                == PhonePendingUrlPolicy.FailedAttemptAction.DROP);
        check(PhonePendingUrlPolicy.afterFailedAttempt(true, 0, 0)
                == PhonePendingUrlPolicy.FailedAttemptAction.DROP);

        System.out.println("Phone pending URL policy assertions passed: " + assertions);
    }

    private static void check(boolean condition) {
        ++assertions;
        if (!condition) {
            throw new AssertionError("assertion " + assertions + " failed");
        }
    }
}
