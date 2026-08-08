// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

import android.content.Context;
import android.content.SharedPreferences;

/** App-private handoff for arguments that must survive a process restart. */
final class RestartArguments {
    static final String EXTRA_INTERNAL_RESTART = "org.overte.pico.INTERNAL_RESTART";
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
        preferences.edit().remove(KEY_ARGUMENTS).apply();
        return arguments;
    }

    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    }
}
