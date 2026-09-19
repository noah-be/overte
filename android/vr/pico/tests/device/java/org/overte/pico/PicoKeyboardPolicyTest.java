// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

public final class PicoKeyboardPolicyTest {
    public static void main(String[] ignored) {
        int forwarded = 0;
        for (int bits = 0; bits < 32; bits++) {
            boolean actual = PicoKeyboardPolicy.forwardToQt((bits & 1) != 0,
                (bits & 2) != 0, (bits & 4) != 0, (bits & 8) != 0, (bits & 16) != 0);
            if (actual) forwarded++;
            if (actual != (bits == 15)) throw new AssertionError("keyboard source/focus boundary failed");
        }
        if (forwarded != 1) throw new AssertionError("missing supported keyboard path");
        System.out.println("PASS production keyboard focus/source policy: 32 combinations");
    }
}
