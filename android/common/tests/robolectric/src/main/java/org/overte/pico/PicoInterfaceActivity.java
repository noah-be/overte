package org.overte.pico;

import android.app.Activity;

/** Boundary stub: the real destination owns Qt/OpenXR and is not host-loadable. */
public final class PicoInterfaceActivity extends Activity {
    // Compile boundary only. No real activity means microphone permission denied.
    public static PicoInterfaceActivity getInstance() { return null; }
}
