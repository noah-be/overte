// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.view.KeyEvent;
import android.view.inputmethod.InputConnection;

/** Native editor operations, never DOM-script interpolation or clipboard access. */
final class PicoTextInput {
    static boolean valid(String value) {
        if (value == null || value.length() > 4096) return false;
        for (int at = 0; at < value.length(); ++at) {
            char unit = value.charAt(at);
            if (Character.isHighSurrogate(unit)) {
                if (++at >= value.length() || !Character.isLowSurrogate(value.charAt(at))) return false;
            } else if (Character.isLowSurrogate(unit)) return false;
            if (Character.isISOControl(unit) && unit != '\n' && unit != '\t') return false;
        }
        return true;
    }
    static boolean text(InputConnection input, String text, boolean composing) {
        if (input == null || !valid(text)) return false;
        if (composing && text.isEmpty()) return input.finishComposingText();
        return composing ? input.setComposingText(text, 1) : input.commitText(text, 1);
    }
    static boolean key(InputConnection input, int key) {
        if (input == null) return false;
        if (key == KeyEvent.KEYCODE_DEL || key == KeyEvent.KEYCODE_FORWARD_DEL) {
            CharSequence selection = input.getSelectedText(0);
            if (selection != null && selection.length() > 0) return input.commitText("", 1);
            return input.deleteSurroundingTextInCodePoints(key == KeyEvent.KEYCODE_DEL ? 1 : 0,
                                                         key == KeyEvent.KEYCODE_FORWARD_DEL ? 1 : 0);
        }
        if (key != KeyEvent.KEYCODE_ENTER && key != KeyEvent.KEYCODE_TAB
                && key != KeyEvent.KEYCODE_DPAD_LEFT && key != KeyEvent.KEYCODE_DPAD_RIGHT
                && key != KeyEvent.KEYCODE_MOVE_HOME && key != KeyEvent.KEYCODE_MOVE_END) return false;
        boolean down = input.sendKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, key));
        boolean up = input.sendKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, key));
        return down && up;
    }
    private PicoTextInput() { }
}
