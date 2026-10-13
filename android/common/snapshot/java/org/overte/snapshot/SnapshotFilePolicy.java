// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.snapshot;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.util.Locale;

/** Mirrors the native SnapshotStorage authority before any platform file access. */
final class SnapshotFilePolicy {
    static final long MAX_BYTES = 256L * 1024 * 1024;
    static File validate(String rootPath, String requested) throws IOException {
        if (rootPath == null || requested == null) throw new IOException("Missing snapshot");
        File root = new File(rootPath).getCanonicalFile(), file = new File(requested);
        if (Files.isSymbolicLink(new File(rootPath).toPath()) || !root.isDirectory() || !file.isAbsolute() || Files.isSymbolicLink(file.toPath())
                || !file.getAbsolutePath().equals(file.getCanonicalPath()) || !root.equals(file.getParentFile())
                || !file.isFile() || file.length() < 1 || file.length() > MAX_BYTES || mime(file) == null)
            throw new IOException("Invalid snapshot");
        return file;
    }
    static String mime(File file) {
        String name = file.getName().toLowerCase(Locale.ROOT);
        if (name.endsWith(".png")) return "image/png";
        if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
        if (name.endsWith(".webp")) return "image/webp";
        if (name.endsWith(".gif")) return "image/gif";
        return null;
    }
}
