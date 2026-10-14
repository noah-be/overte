// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

/** Inactive lifecycle revisions are valid only for the exact instance and owner. */
final class WebLifecycleDispatch {
    static boolean apply(Object expected, Object current, Object owner, Object currentOwner,
            Object activity, Object currentActivity, long revision, long actualRevision, Runnable effect) {
        if (expected == null || expected != current || owner == null || owner != currentOwner
                || activity == null || activity != currentActivity || revision <= 0 || revision != actualRevision) return false;
        effect.run(); return true;
    }
}
