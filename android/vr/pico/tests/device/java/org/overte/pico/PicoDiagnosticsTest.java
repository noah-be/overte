// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;
import android.util.Log;
import org.overte.security.SafeDiagnostics;
import org.overte.security.SafeDiagnostics.Event;
public final class PicoDiagnosticsTest {
    static void check(String level, Event event) {
        if (!"OvertePico".equals(Log.tag) || !level.equals(Log.level)
                || !SafeDiagnostics.event(event).equals(Log.text)
                || !SafeDiagnostics.sanitize(Log.text).equals(Log.text)) throw new AssertionError("sink contract");
    }
    public static void main(String[] args) {
        for (Event event : Event.values()) {
            RedactingDiagnostics.e(event); check("E", event);
            RedactingDiagnostics.w(event); check("W", event);
            RedactingDiagnostics.i(event); check("I", event);
        }
        RedactingDiagnostics.e(null); check("E", null);
        for (java.lang.reflect.Method method : RedactingDiagnostics.class.getDeclaredMethods()) {
            if (method.getParameterTypes().length != 1 || method.getParameterTypes()[0] != Event.class) {
                throw new AssertionError("no payload/context/exception sink overload");
            }
        }
        System.out.println("Pico production Android log wrapper PASS (captured sink, not logcat)");
    }
}
