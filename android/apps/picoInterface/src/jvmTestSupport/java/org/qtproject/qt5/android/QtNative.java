package org.qtproject.qt5.android;

import android.app.Activity;

/** Minimal JVM-test substitute for the class normally supplied by Qt's Android JAR. */
public final class QtNative {
    private QtNative() {
    }

    public static void terminateQt() {
    }

    public static void setActivity(Activity activity, Object delegate) {
    }
}
