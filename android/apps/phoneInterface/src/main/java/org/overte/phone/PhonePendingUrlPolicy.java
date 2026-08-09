package org.overte.phone;

/** Pure lifecycle and retry decisions for Android-to-native URL delivery. */
final class PhonePendingUrlPolicy {
    enum FailedAttemptAction {
        RETRY,
        DROP
    }

    private PhonePendingUrlPolicy() {
    }

    static boolean canAttempt(String pendingUrl, boolean resumed) {
        return pendingUrl != null && resumed;
    }

    static FailedAttemptAction afterFailedAttempt(
            boolean resumed, int failedAttempts, int maximumAttempts) {
        return resumed && failedAttempts < maximumAttempts
                ? FailedAttemptAction.RETRY
                : FailedAttemptAction.DROP;
    }
}
