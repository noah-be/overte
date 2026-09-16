package org.overte.phone;

import android.util.Log;
import org.overte.security.SafeDiagnostics;

/** Phone logcat boundary. No dynamic tags, Throwable or secondary context. */
public final class RedactingDiagnostics {
    private static final String TAG = "OvertePhone";
    private RedactingDiagnostics() { }

    public static void event(SafeDiagnostics.Event event) {
        write(Log.INFO, SafeDiagnostics.event(event));
    }

    public static void warning(String untrusted) {
        write(Log.WARN, SafeDiagnostics.sanitize(untrusted));
    }

    static void storageFailure(SecureAccountStore.Failure failure) {
        SafeDiagnostics.Event event;
        switch (failure) {
            case CORRUPT:
            case MISSING_KEY:
            case INPUT:
                event = SafeDiagnostics.Event.STORAGE_CORRUPT;
                break;
            default:
                event = SafeDiagnostics.Event.STORAGE_UNAVAILABLE;
        }
        write(Log.WARN, SafeDiagnostics.event(event));
    }

    private static void write(int priority, String safe) {
        try {
            Log.println(priority, TAG, safe);
        } catch (RuntimeException unavailable) {
            // An unavailable sink drops output. Never fall back to stderr or
            // forward this exception (or the original payload) elsewhere.
        }
    }
}
