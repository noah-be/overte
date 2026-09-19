// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

import android.content.Context;
import android.content.SharedPreferences;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;

/** App-private handoff for arguments that must survive a process restart. */
final class RestartArguments {
    private static final String PREFERENCES = "pico_restart";
    private static final String KEY_ARGUMENTS = "arguments";
    private static final String SLOT = "restart-arguments";

    private RestartArguments() {
    }

    static synchronized boolean store(Context context, String arguments) {
        String safeArguments = PicoRestartUrlPolicy.arguments(arguments);
        if (safeArguments == null) return false;
        byte[] bytes = safeArguments.getBytes(StandardCharsets.UTF_8);
        try {
            // Old transient handoffs are discarded, never imported as trusted input.
            if (!preferences(context).edit().remove(KEY_ARGUMENTS).commit()) return false;
            new SecureAccountStore(context).write(SLOT, bytes);
            return true;
        } catch (IOException | GeneralSecurityException | RuntimeException error) {
            return false;
        } finally {
            Arrays.fill(bytes, (byte) 0);
        }
    }

    static synchronized String consume(Context context) {
        byte[] bytes = null;
        try {
            if (!preferences(context).edit().remove(KEY_ARGUMENTS).commit()) return null;
            SecureAccountStore store = new SecureAccountStore(context);
            bytes = store.read(SLOT);
            store.remove(SLOT);
            return bytes == null ? null : PicoRestartUrlPolicy.arguments(
                new String(bytes, StandardCharsets.UTF_8));
        } catch (IOException | GeneralSecurityException | RuntimeException error) {
            return null;
        } finally {
            if (bytes != null) Arrays.fill(bytes, (byte) 0);
        }
    }

    static synchronized boolean clear(Context context) {
        try {
            boolean legacyRemoved = preferences(context).edit().remove(KEY_ARGUMENTS).commit();
            new SecureAccountStore(context).remove(SLOT);
            return legacyRemoved;
        } catch (IOException | GeneralSecurityException | RuntimeException error) {
            return false;
        }
    }

    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    }
}
