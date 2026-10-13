// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

/** Source-grant lifetime and actual page lifetime are deliberately independent. */
final class WebDocumentState {
    private long grant;
    private long page;
    private boolean visible = true;
    private boolean active = true;
    synchronized long begin(long nextGrant) {
        grant = nextGrant;
        if (page < Long.MAX_VALUE) ++page;
        else active = false;
        return page;
    }
    synchronized void grant(long nextGrant) { grant = nextGrant; }
    synchronized void visible(boolean value) { visible = value; }
    synchronized void close() { active = false; grant = 0; }
    synchronized long grant() { return grant; }
    synchronized long page() { return page; }
    synchronized boolean admits(long expectedGrant, long expectedPage, boolean mainFrame, int bytes) {
        return active && visible && grant > 0 && expectedGrant == grant
            && page > 0 && expectedPage == page && mainFrame && bytes > 0 && bytes <= 65536;
    }
}
