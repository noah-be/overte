// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
/** Only the Android OS exporter is substituted; production Qt owner/JNI calls remain real. */
public final class SnapshotBoundary {
    public static long handle, ticket, cancelled;
    public static String root, path, action;
    public static void request(long owner, long request, String storageRoot, String file, String operation) {
        handle = owner; ticket = request; root = storageRoot; path = file; action = operation;
    }
    public static void cancel(long owner, long request) { if (owner == handle) cancelled = request; }
}
