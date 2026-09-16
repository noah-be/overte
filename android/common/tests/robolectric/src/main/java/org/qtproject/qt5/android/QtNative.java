package org.qtproject.qt5.android;

/** Compile boundary: host tests never initialize the Qt native runtime. */
public final class QtNative {
    public static void setApplicationState(int state) {
        throw new AssertionError("Qt native lifecycle must be exercised on an Android device");
    }
}
