// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

/** One texture pointer gesture; hover never manufactures a touch down. */
final class WebPointerState {
    private boolean pressed, hovering;
    private long downTime;
    static boolean hover(int action) { return action == 9 || action == 7 || action == 10; }
    boolean pressed() { return pressed; }
    boolean hovering() { return hovering; }
    long downTime() { return downTime; }
    boolean accept(int action, long now) {
        if (hover(action)) { hovering = action != 10; return true; }
        if (action == 0) { pressed = true; downTime = now; return true; }
        if (action == 2) return pressed;
        if (action == 1 || action == 3) {
            if (!pressed) return false;
            pressed = false; return true;
        }
        return false;
    }
}
