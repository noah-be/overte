// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "RedactingDiagnostics.h"
#include <os/log.h>

namespace overte::ios {
void logDiagnostic(DiagnosticEvent event) noexcept {
    const char* safe = diagnosticEventCode(event);
    logRedactedDiagnostic(safe, std::strlen(safe));
}
void logSharedDiagnostic(security::DiagnosticEvent event) noexcept {
    const char* safe = security::diagnosticEvent(event);
    logRedactedDiagnostic(safe, std::strlen(safe));
}
void logRedactedDiagnostic(const char* payload, std::size_t length) noexcept {
    static os_log_t log = os_log_create("org.overte.interface", "diagnostics");
    // No NSError, endpoint, native status string, selector, account or device ID.
    os_log_info(log, "%{public}s", security::sanitizeDiagnostic(payload, length));
}
} // namespace overte::ios
