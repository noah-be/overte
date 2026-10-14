// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.snapshot;

import android.app.Activity;

/** Immutable product Activity owner; OS callbacks must return through that owner. */
public interface SnapshotHost {
    Activity activity();
    boolean isForeground();
}
