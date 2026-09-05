// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "RedactingDiagnostics.h"
#import <os/log.h>

namespace overte::ios {
void logDiagnostic(DiagnosticEvent event) noexcept {
    static os_log_t log = os_log_create("org.overte.interface", "diagnostics");
    // No NSError, endpoint, native status string, selector, account or device ID.
    os_log_error(log, "event=%{public}s", diagnosticEventCode(event));
}
} // namespace overte::ios
