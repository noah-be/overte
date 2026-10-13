// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

/** One OS picker lease, never rebound to another callback after Activity recreation. */
public final class WebFilePickerState<T> {
    private static final AtomicInteger NEXT_REQUEST = new AtomicInteger(0x5742);
    private int request;
    private Consumer<T> callback;
    private boolean returned;
    private T selected;
    public int begin(Consumer<T> result) {
        if (callback != null || result == null) return 0;
        int candidate = NEXT_REQUEST.getAndUpdate(value -> value < 0x8000 ? value + 1 : value);
        if (candidate > 0x7fff) return 0;
        request = candidate; callback = result; returned = false; selected = null;
        return request;
    }
    public boolean owns(int requestCode) { return callback != null && requestCode == request; }
    public boolean receive(int requestCode, T values, boolean foreground) {
        if (callback == null || requestCode != request || returned) return false;
        selected = values; returned = true; deliver(foreground); return true;
    }
    public void deliver(boolean foreground) {
        if (!foreground || !returned || callback == null) return;
        Consumer<T> result = callback; T values = selected;
        callback = null; selected = null; returned = false; request = 0;
        result.accept(values);
    }
    public void cancel() {
        Consumer<T> result = callback;
        callback = null; selected = null; returned = false; request = 0;
        if (result != null) result.accept(null);
    }
}
