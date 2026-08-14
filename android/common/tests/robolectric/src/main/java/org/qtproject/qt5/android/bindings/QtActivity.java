package org.qtproject.qt5.android.bindings;

import android.app.Activity;

/**
 * Compile boundary for Qt 5's Android Activity. Robolectric compiles the real
 * PhoneInterfaceActivity but does not initialize its native-library owner.
 */
public class QtActivity extends Activity {
    public static String APPLICATION_PARAMETERS;
}
