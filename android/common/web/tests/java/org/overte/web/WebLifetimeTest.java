// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;
public final class WebLifetimeTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] arguments) {
        Object first = new Object(), second = new Object();
        WebInputGate gate = new WebInputGate();
        check(gate.capture() == null); gate.update(first, true);
        WebInputGate.Ticket gesture = gate.capture(); check(gate.permits(gesture, first));
        gate.update(first, false); check(!gate.permits(gesture, first));
        gate.update(first, true); check(!gate.permits(gesture, first));
        gesture = gate.capture(); gate.update(second, true); check(!gate.permits(gesture, second));
        WebDocumentState document = new WebDocumentState();
        long page = document.begin(4); check(document.admits(4, page, true, 65536));
        check(!document.admits(4, page, false, 4)); check(!document.admits(4, page, true, 65537));
        long next = document.begin(4); check(!document.admits(4, page, true, 4));
        document.visible(false); check(!document.admits(4, next, true, 4));
        document.visible(true); document.grant(6); check(!document.admits(4, next, true, 4));
        check(document.admits(6, next, true, 4)); document.close(); check(!document.admits(6, next, true, 4));
        System.out.println("PASS: queued input ownership, page epochs, foreground grants and bounded messages");
    }
}
