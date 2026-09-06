// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.util.Log;
import org.overte.security.SafeDiagnostics;
import org.overte.security.SafeDiagnostics.Event;

/** Actual Pico Android sink. No overload accepts a tag, payload or Throwable. */
public final class RedactingDiagnostics {
    private static final String TAG = "OvertePico";
    private RedactingDiagnostics() { }
    public static void e(Event event) { Log.e(TAG, SafeDiagnostics.sanitize(SafeDiagnostics.event(event))); }
    public static void w(Event event) { Log.w(TAG, SafeDiagnostics.sanitize(SafeDiagnostics.event(event))); }
    public static void i(Event event) { Log.i(TAG, SafeDiagnostics.sanitize(SafeDiagnostics.event(event))); }
}
