// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.snapshot;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Explicit non-exported target of the one-shot system chooser callback. */
public final class SnapshotShareReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        SnapshotAdapter.shareChosen(context, intent);
    }
}
