// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;
import java.util.ArrayList;
import java.util.List;

/** Bounded URLs only; never restores POST bodies, form state or running documents. */
final class WebNavigationArchive {
    private final List<String> urls = new ArrayList<>();
    private int index = -1;
    void remember(List<String> entries, int selected) {
        urls.clear(); index = -1;
        if (selected < 0 || selected >= entries.size()) return;
        int start = Math.max(0, selected - 63), end = Math.min(entries.size(), start + 128);
        for (int i = start; i < end; i++) urls.add(entries.get(i));
        index = selected - start;
    }
    void visit(String url) {
        if (url == null || index >= 0 && url.equals(urls.get(index))) return;
        while (urls.size() > index + 1) urls.remove(urls.size() - 1);
        urls.add(url); index++;
        if (urls.size() > 128) { urls.remove(0); index--; }
    }
    boolean back() { return index > 0; }
    boolean forward() { return index >= 0 && index + 1 < urls.size(); }
    String peek(int delta) {
        int next = index + delta;
        return next < 0 || next >= urls.size() ? null : urls.get(next);
    }
    String select(int delta) {
        int next = index + delta;
        if (next < 0 || next >= urls.size()) return null;
        index = next; return urls.get(index);
    }
}
