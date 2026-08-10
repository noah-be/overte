// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

public final class PicoTouchStateTest {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        PicoTouchState state = new PicoTouchState();
        require(!state.isActive(), "new state must be idle");
        require(state.downTimeFor(PicoTouchState.ACTION_DOWN, 100) == 100,
            "down starts the gesture");
        require(state.isActive(), "down must activate the gesture");
        require(state.downTimeFor(PicoTouchState.ACTION_MOVE, 120) == 100,
            "move must retain downTime");
        require(state.downTimeFor(PicoTouchState.ACTION_UP, 140) == 100,
            "up must retain downTime");
        require(!state.isActive(), "up must end the gesture");

        require(state.downTimeFor(PicoTouchState.ACTION_DOWN, 200) == 200,
            "a later gesture needs a fresh downTime");
        require(state.downTimeFor(PicoTouchState.ACTION_CANCEL, 210) == 200,
            "cancel must retain downTime");
        require(!state.isActive(), "cancel must end the gesture");

        require(state.downTimeFor(PicoTouchState.ACTION_MOVE, 300) == 300,
            "an orphan move must fail closed to its own eventTime");
        require(!state.isActive(), "an orphan move must not start a gesture");

        require(state.downTimeFor(PicoTouchState.ACTION_DOWN, 400) == 400,
            "replacement setup must start a gesture");
        require(state.downTimeFor(PicoTouchState.ACTION_CANCEL, 410) == 400,
            "a replacement down must first cancel with the original downTime");
        require(state.downTimeFor(PicoTouchState.ACTION_DOWN, 411) == 411,
            "replacement down must start a fresh gesture");
    }
}
