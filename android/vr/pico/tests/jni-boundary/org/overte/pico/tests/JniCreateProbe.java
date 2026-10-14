// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.pico.tests;
import android.os.Handler;
import java.lang.reflect.Field;
/** Inspect the command captured from the actual production create method. */
public final class JniCreateProbe {
    public static boolean verify() throws ReflectiveOperationException {
        Runnable command = Handler.posted;
        if (command == null) return false;
        boolean url = false, agent = false, bridge = false, editor = false;
        int positiveLongs = 0;
        for (Field field : command.getClass().getDeclaredFields()) {
            field.setAccessible(true);
            Object value = field.get(command);
            if (value instanceof String) {
                String text = (String) value;
                url |= text.equals("https://example.invalid/pico-jni");
                agent |= text.equals("Pico JNI production binding test");
                bridge |= text.contains("__overteTransport") && !text.contains("__overteEditorTransport");
                editor |= text.contains("__overteEditorTransport") && text.contains("__overteEditor");
            } else if (value instanceof Long && ((Long) value) > 0) {
                ++positiveLongs;
            }
        }
        return url && agent && bridge && editor && positiveLongs == 2;
    }
}
