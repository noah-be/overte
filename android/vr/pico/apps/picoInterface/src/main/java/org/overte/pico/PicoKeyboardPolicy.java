// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

/** Only actual external alphabetic keyboards may enter Qt's Android key queue. */
final class PicoKeyboardPolicy {
    private PicoKeyboardPolicy() { }

    static boolean forwardToQt(boolean focused, boolean external,
            boolean alphabetic, boolean keyboardSource, boolean gamepadSource) {
        return focused && external && alphabetic && keyboardSource && !gamepadSource;
    }
}
