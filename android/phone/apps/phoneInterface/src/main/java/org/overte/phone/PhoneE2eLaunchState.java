package org.overte.phone;

/** Process-only handshake between the debug E2E activities and Qt activity. */
final class PhoneE2eLaunchState {
    static final int RESTORE_STORED_PREFERENCE = -1;
    static final int PREPARE_GROUNDED_FIXTURE = 0;
    static final int ENABLE_E2E_FLIGHT = 1;

    private static boolean active;
    private static Integer pendingFlyingOverride;

    private PhoneE2eLaunchState() {
    }

    static synchronized void begin() {
        active = true;
        pendingFlyingOverride = PREPARE_GROUNDED_FIXTURE;
    }

    static synchronized boolean requestFlyingOverride(int mode) {
        if (!active || mode < RESTORE_STORED_PREFERENCE || mode > ENABLE_E2E_FLIGHT) {
            return false;
        }
        pendingFlyingOverride = mode;
        return true;
    }

    static synchronized Integer takePendingFlyingOverride() {
        Integer result = pendingFlyingOverride;
        pendingFlyingOverride = null;
        return active ? result : null;
    }

    static synchronized void finishRestore() {
        active = false;
        pendingFlyingOverride = null;
    }

    static synchronized boolean isActive() {
        return active;
    }

    static synchronized void resetForTest() {
        active = false;
        pendingFlyingOverride = null;
    }
}
