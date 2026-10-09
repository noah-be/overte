package org.qtproject.qt5.android;

/** Compile boundary: host tests never initialize the Qt native runtime. */
public final class QtNative {
    /** No Qt Activity owns the host runtime; native initialization stays device-owned. */
    public static android.app.Activity activity() {
        return null;
    }

    public static void setApplicationState(int state) {
        throw new AssertionError("Qt native lifecycle must be exercised on an Android device");
    }
}
