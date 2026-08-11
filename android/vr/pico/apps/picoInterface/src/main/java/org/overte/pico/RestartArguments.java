// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

import android.content.Context;
import android.content.SharedPreferences;

/** App-private handoff for arguments that must survive a process restart. */
final class RestartArguments {
    private static final String PREFERENCES = "pico_restart";
    private static final String KEY_ARGUMENTS = "arguments";

    private RestartArguments() {
    }

    static boolean store(Context context, String arguments) {
        return preferences(context).edit()
            .putString(KEY_ARGUMENTS, arguments == null ? "" : arguments)
            .commit();
    }

    static String consume(Context context) {
        SharedPreferences preferences = preferences(context);
        String arguments = preferences.getString(KEY_ARGUMENTS, null);
        return preferences.edit().remove(KEY_ARGUMENTS).commit() ? arguments : null;
    }

    static boolean clear(Context context) {
        return preferences(context).edit().remove(KEY_ARGUMENTS).commit();
    }

    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    }
}
