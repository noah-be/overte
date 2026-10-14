// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;
/** Shared AndroidX runtime boundary for the SDK-only Pico caller compile test.
 * The full production runtime is compiled by the separate actual WebKit API check.
 */
public final class EmbeddedWebView {
    public static void initialize(EmbeddedWebHost host) { }
    public static void setForeground(EmbeddedWebHost host, boolean active) { }
    public static void detach(EmbeddedWebHost host) { }
}
