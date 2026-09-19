// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../../../../../security/redaction/SafeDiagnostics.h"
#include <android/log.h>

namespace overte { namespace pico {
inline void diagnosticError(security::DiagnosticEvent event) noexcept {
    __android_log_write(ANDROID_LOG_ERROR, "OvertePico", security::diagnosticEvent(event));
}
inline void diagnosticWarning(security::DiagnosticEvent event) noexcept {
    __android_log_write(ANDROID_LOG_WARN, "OvertePico", security::diagnosticEvent(event));
}
}}
