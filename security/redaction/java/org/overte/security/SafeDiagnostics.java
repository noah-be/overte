// SPDX-License-Identifier: Apache-2.0
package org.overte.security;

/** Closed event output only. Never forwards Throwable, message, URL or context. */
public final class SafeDiagnostics {
    private SafeDiagnostics() { }
    public enum Event {
        REDACTED, AUTH_REQUIRED, AUTH_CANCELLED, AUTH_FAILED, AUTH_READY,
        STORAGE_UNAVAILABLE, STORAGE_CORRUPT, STORAGE_CLEARED,
        PERMISSION_DENIED, PERMISSION_GRANTED, AUDIO_STOPPED, AUDIO_INTERRUPTED,
        LIFECYCLE_SUSPENDED, LIFECYCLE_RESUMED, CONNECTION_FAILED,
        CONNECTION_READY, URL_REJECTED, CALLBACK_DISCARDED
    }
    public static String event(Event event) {
        return event == null ? "OVT_REDACTED" : "OVT_" + event.name();
    }
    public static String sanitize(String untrusted) {
        if (untrusted == null || untrusted.length() > 32) { return "OVT_REDACTED"; }
        for (Event event : Event.values()) {
            String safe = event(event);
            if (safe.equals(untrusted)) { return safe; }
        }
        return "OVT_REDACTED";
    }
}
