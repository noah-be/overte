// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

/** Framework-free launch decisions used by {@link PicoInterfaceActivity}. */
final class PicoInterfaceActivityPolicy {
    static final String DEFAULT_APPLICATION_ARGUMENTS = "--display=OpenXR";

    private PicoInterfaceActivityPolicy() {
    }

    static String applicationParameters(
            boolean hasApplicationArguments, String applicationArguments,
            String cacheDirectory) {
        String requestedParameters = hasApplicationArguments && applicationArguments != null
                ? applicationArguments
                : DEFAULT_APPLICATION_ARGUMENTS;
        return requestedParameters + " --cache " + cacheDirectory;
    }

    static boolean canUseExactRestart(int sdkInt, boolean canScheduleExactAlarms) {
        return sdkInt < 31 || canScheduleExactAlarms;
    }
}
