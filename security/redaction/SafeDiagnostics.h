// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstddef>
#include <cstring>

namespace overte { namespace security {
enum class DiagnosticEvent {
    Redacted, AuthRequired, AuthCancelled, AuthFailed, AuthReady, StorageUnavailable,
    StorageCorrupt, StorageCleared, PermissionDenied, PermissionGranted,
    AudioStopped, AudioInterrupted, LifecycleSuspended, LifecycleResumed,
    ConnectionFailed, ConnectionReady, UrlRejected, CallbackDiscarded
};

inline const char* diagnosticEvent(DiagnosticEvent event) noexcept {
    switch (event) {
        case DiagnosticEvent::AuthRequired: return "OVT_AUTH_REQUIRED";
        case DiagnosticEvent::AuthCancelled: return "OVT_AUTH_CANCELLED";
        case DiagnosticEvent::AuthFailed: return "OVT_AUTH_FAILED";
        case DiagnosticEvent::AuthReady: return "OVT_AUTH_READY";
        case DiagnosticEvent::StorageUnavailable: return "OVT_STORAGE_UNAVAILABLE";
        case DiagnosticEvent::StorageCorrupt: return "OVT_STORAGE_CORRUPT";
        case DiagnosticEvent::StorageCleared: return "OVT_STORAGE_CLEARED";
        case DiagnosticEvent::PermissionDenied: return "OVT_PERMISSION_DENIED";
        case DiagnosticEvent::PermissionGranted: return "OVT_PERMISSION_GRANTED";
        case DiagnosticEvent::AudioStopped: return "OVT_AUDIO_STOPPED";
        case DiagnosticEvent::AudioInterrupted: return "OVT_AUDIO_INTERRUPTED";
        case DiagnosticEvent::LifecycleSuspended: return "OVT_LIFECYCLE_SUSPENDED";
        case DiagnosticEvent::LifecycleResumed: return "OVT_LIFECYCLE_RESUMED";
        case DiagnosticEvent::ConnectionFailed: return "OVT_CONNECTION_FAILED";
        case DiagnosticEvent::ConnectionReady: return "OVT_CONNECTION_READY";
        case DiagnosticEvent::UrlRejected: return "OVT_URL_REJECTED";
        case DiagnosticEvent::CallbackDiscarded: return "OVT_CALLBACK_DISCARDED";
        default: return "OVT_REDACTED";
    }
}

// Arbitrary payload is never retained or partially reproduced. Returned storage
// is a static constant, independent of input lifetime. No dynamic configuration.
inline const char* sanitizeDiagnostic(const char* bytes, std::size_t size) noexcept {
    if (!bytes || size > 32) { return diagnosticEvent(DiagnosticEvent::Redacted); }
    for (int i = 0; i <= static_cast<int>(DiagnosticEvent::CallbackDiscarded); ++i) {
        const char* safe = diagnosticEvent(static_cast<DiagnosticEvent>(i));
        if (std::strlen(safe) == size && std::memcmp(bytes, safe, size) == 0) { return safe; }
    }
    return diagnosticEvent(DiagnosticEvent::Redacted);
}
}} // namespace overte::security
