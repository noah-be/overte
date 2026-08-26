// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

/** Framework-free launch decisions used by {@link PicoInterfaceActivity}. */
final class PicoInterfaceActivityPolicy {
    static final String DEFAULT_APPLICATION_ARGUMENTS = "--display=OpenXR";

    private PicoInterfaceActivityPolicy() {
    }

    static String applicationParameters(String cacheDirectory) {
        // QtActivityLoader appends the trusted applicationArguments Intent
        // extra. Keep only the invariant base arguments here so argv is never
        // duplicated during a restart or debug E2E launch.
        return DEFAULT_APPLICATION_ARGUMENTS + " --cache " + cacheDirectory;
    }

    static boolean canUseExactRestart(int sdkInt, boolean canScheduleExactAlarms) {
        return sdkInt < 31 || canScheduleExactAlarms;
    }
}
