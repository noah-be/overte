// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
/** Explicit OS endpoint fixture; production Qt helper, bridge and JNI remain actual. */
public final class DocumentBoundary {
    public static String request, root, caption, filter, cancelled;
    public static boolean multiple;
    public static void requestTree(String id, String location, String title) {
        request=id; root=location; caption=title; filter=""; multiple=false;
    }
    public static void request(String id, String location, String title, String types, boolean many) {
        request=id; root=location; caption=title; filter=types; multiple=many;
    }
    public static void cancel(String id) { cancelled=id; }
}
