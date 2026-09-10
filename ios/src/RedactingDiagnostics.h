// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../security/redaction/SafeDiagnostics.h"

namespace overte::ios {
// Local call sites map to the pinned PX-16 event vocabulary.
enum class DiagnosticEvent {
    AudioConfigurationFailed, AudioActivationFailed, AudioDeactivationFailed,
    ApplicationSupportUnavailable, DirectoryLookupFailed, DirectoryResponseInvalid,
    SecureStorageUnavailable, RecoveryExhausted
};
inline const char* diagnosticEventCode(DiagnosticEvent event) noexcept {
    using Shared = security::DiagnosticEvent;
    switch (event) {
        case DiagnosticEvent::AudioConfigurationFailed:
        case DiagnosticEvent::AudioActivationFailed:
        case DiagnosticEvent::AudioDeactivationFailed: return security::diagnosticEvent(Shared::AudioStopped);
        case DiagnosticEvent::ApplicationSupportUnavailable:
        case DiagnosticEvent::SecureStorageUnavailable: return security::diagnosticEvent(Shared::StorageUnavailable);
        case DiagnosticEvent::DirectoryLookupFailed:
        case DiagnosticEvent::DirectoryResponseInvalid:
        case DiagnosticEvent::RecoveryExhausted: return security::diagnosticEvent(Shared::ConnectionFailed);
    }
    return security::diagnosticEvent(Shared::Redacted);
}
void logDiagnostic(DiagnosticEvent event) noexcept;
void logSharedDiagnostic(security::DiagnosticEvent event) noexcept;
void logRedactedDiagnostic(const char* payload, std::size_t length) noexcept;
} // namespace overte::ios
