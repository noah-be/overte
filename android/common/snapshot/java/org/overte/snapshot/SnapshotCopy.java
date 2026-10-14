// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.snapshot;

import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.util.function.BooleanSupplier;

/** Success is returned only after bounded copying, flush and destination close. */
final class SnapshotCopy {
    static void copy(InputStream input, OutputStream output, BooleanSupplier cancelled) throws IOException {
        try (InputStream source = input; OutputStream destination = output) {
            if (destination == null) throw new IOException("Destination unavailable");
            byte[] buffer = new byte[65536]; long total = 0; int count;
            while ((count = source.read(buffer)) != -1) {
                if (cancelled.getAsBoolean() || (total += count) > SnapshotFilePolicy.MAX_BYTES)
                    throw new IOException("Cancelled or oversized export");
                destination.write(buffer, 0, count);
            }
            if (total == 0 || cancelled.getAsBoolean()) throw new IOException("Empty or cancelled export");
            destination.flush();
        }
    }
}
