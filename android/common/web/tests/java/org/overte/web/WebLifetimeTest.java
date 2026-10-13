// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;
public final class WebLifetimeTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] arguments) {
        WebTextureScale scale = new WebTextureScale(4096, 2048, 2.5f);
        check(scale.width == 2048 && scale.height == 1024 && scale.layoutWidth == 5120 && scale.layoutHeight == 2560);
        check(scale.pointer(100) == 250);
        scale = new WebTextureScale(400, 300, 1.5f);
        check(scale.width == 400 && scale.layoutWidth == 600 && scale.layoutHeight == 450 && scale.pointer(20) == 30);
        for (float invalid : new float[]{0, -1, Float.NaN, Float.POSITIVE_INFINITY, 100}) {
            boolean denied = false;
            try { new WebTextureScale(2048, 1024, invalid); } catch (IllegalArgumentException expected) { denied = true; }
            check(denied);
        }
        java.util.ArrayList<String> selections = new java.util.ArrayList<>();
        WebFilePickerState<String> picker = new WebFilePickerState<>();
        int request = picker.begin(selections::add);
        check(request != 0 && picker.begin(selections::add) == 0);
        check(!picker.receive(request + 1, "foreign", true));
        check(picker.receive(request, "selected", false) && selections.isEmpty());
        check(!picker.receive(request, "duplicate", true)); picker.deliver(true);
        check(selections.size() == 1 && "selected".equals(selections.get(0)));
        picker.deliver(true); picker.cancel(); check(selections.size() == 1);
        int nextRequest = picker.begin(selections::add); check(nextRequest > request);
        check(!picker.receive(request, "old", true)); picker.cancel();
        check(selections.size() == 2 && selections.get(1) == null);
        WebFilePickerState<String> replacement = new WebFilePickerState<>();
        int third = replacement.begin(selections::add); check(third > nextRequest);
        check(!replacement.receive(nextRequest, "old Activity", true));
        check(replacement.receive(third, null, true) && selections.size() == 3 && selections.get(2) == null);
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
        Object view = new Object();
        WebFileChoiceLease selected = new WebFileChoiceLease(view, first, 7, "source-A", "https://one.test/page");
        check(selected.consume(view, first, 7, "source-A", "https://one.test/page", true, true, true, true, true) == 2);
        check(selected.consume(view, first, 7, "source-A", "https://one.test/page", true, true, true, true, true) == 0);
        selected = new WebFileChoiceLease(view, first, 7, "source-A", "https://one.test/page");
        check(selected.consume(view, first, 8, "source-A", "https://one.test/page", true, true, true, true, true) == 1);
        selected = new WebFileChoiceLease(view, first, 7, "source-A", "https://one.test/page");
        check(selected.consume(view, second, 7, "source-A", "https://one.test/page", true, true, true, true, true) == 1);
        selected = new WebFileChoiceLease(view, first, 7, "source-A", "https://one.test/page");
        check(selected.consume(view, first, 7, "source-B", "https://one.test/page", true, true, true, true, true) == 1);
        selected = new WebFileChoiceLease(view, first, 7, "source-A", "https://one.test/page");
        check(selected.consume(view, first, 7, "source-A", "https://foreign.test/page", true, true, true, true, true) == 1);
        selected = new WebFileChoiceLease(view, first, 7, "source-A", "https://one.test/page");
        check(selected.consume(view, first, 7, "source-A", "https://one.test/page", true, true, true, true, false) == 1);
        System.out.println("PASS: queued input ownership, page epochs, foreground grants and bounded messages");
    }
}
