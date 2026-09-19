// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

/** Actual SH-006 v001 gate; implemented in picoOpenXR, no Java policy clone. */
final class PicoAudioLifecycle {
    private PicoAudioLifecycle() { }
    static native void foreground(boolean active);
    static native boolean begin(boolean permission);
    static native boolean mayCapture();
    static native void revoke();
    static native void invalidate();
    static native void failed();
    static native void stopCompleted(boolean success);
}
