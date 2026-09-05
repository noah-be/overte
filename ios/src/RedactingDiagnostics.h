// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

namespace overte::ios {
// Local native events take no free-form payload. Shared PX-16 binding is separate.
enum class DiagnosticEvent {
    AudioConfigurationFailed, AudioActivationFailed, AudioDeactivationFailed,
    ApplicationSupportUnavailable, DirectoryLookupFailed, DirectoryResponseInvalid,
    SecureStorageUnavailable, RecoveryExhausted
};
constexpr const char* diagnosticEventCode(DiagnosticEvent event) noexcept {
    switch (event) {
        case DiagnosticEvent::AudioConfigurationFailed: return "audio_configuration_failed";
        case DiagnosticEvent::AudioActivationFailed: return "audio_activation_failed";
        case DiagnosticEvent::AudioDeactivationFailed: return "audio_deactivation_failed";
        case DiagnosticEvent::ApplicationSupportUnavailable: return "application_support_unavailable";
        case DiagnosticEvent::DirectoryLookupFailed: return "directory_lookup_failed";
        case DiagnosticEvent::DirectoryResponseInvalid: return "directory_response_invalid";
        case DiagnosticEvent::SecureStorageUnavailable: return "secure_storage_unavailable";
        case DiagnosticEvent::RecoveryExhausted: return "recovery_exhausted";
    }
    return "unknown_event";
}
void logDiagnostic(DiagnosticEvent event) noexcept;
} // namespace overte::ios
