// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.snapshot;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;

public final class SnapshotPolicyTest {
    private static void check(boolean condition) { if (!condition) throw new AssertionError(); }
    private static void denied(Path root, Path file) throws Exception {
        boolean rejected = false;
        try { SnapshotFilePolicy.validate(root.toString(), file.toString()); } catch (IOException expected) { rejected = true; }
        check(rejected);
    }
    public static void main(String[] arguments) throws Exception {
        Path temporary = Files.createTempDirectory("overte-snapshot-policy-");
        try {
            final boolean[] closed = { false };
            java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream() {
                @Override public void close() { closed[0] = true; }
            };
            SnapshotCopy.copy(new java.io.ByteArrayInputStream(new byte[]{1, 2, 3}), output, () -> false);
            check(closed[0] && java.util.Arrays.equals(output.toByteArray(), new byte[]{1, 2, 3}));
            boolean copyFailed = false;
            try { SnapshotCopy.copy(new java.io.ByteArrayInputStream(new byte[]{1}), new java.io.OutputStream() {
                @Override public void write(int value) throws IOException { throw new IOException("Write failure"); }
            }, () -> false); } catch (IOException expected) { copyFailed = true; }
            check(copyFailed);
            copyFailed = false;
            try { SnapshotCopy.copy(new java.io.ByteArrayInputStream(new byte[]{1}), new java.io.ByteArrayOutputStream() {
                @Override public void close() throws IOException { throw new IOException("Close failure"); }
            }, () -> false); } catch (IOException expected) { copyFailed = true; }
            check(copyFailed);
            copyFailed = false;
            try { SnapshotCopy.copy(new java.io.ByteArrayInputStream(new byte[]{1}), new java.io.ByteArrayOutputStream(), () -> true); }
            catch (IOException expected) { copyFailed = true; } check(copyFailed);
            copyFailed = false;
            try { SnapshotCopy.copy(new java.io.ByteArrayInputStream(new byte[0]), new java.io.ByteArrayOutputStream(), () -> false); }
            catch (IOException expected) { copyFailed = true; } check(copyFailed);
            Path root = Files.createDirectory(temporary.resolve("Snapshots"));
            Path image = Files.write(root.resolve("capture.PNG"), new byte[]{1, 2, 3});
            check(SnapshotFilePolicy.validate(root.toString(), image.toString()).equals(image.toFile()));
            check("image/png".equals(SnapshotFilePolicy.mime(image.toFile())));
            Path outside = Files.write(temporary.resolve("outside.png"), new byte[]{1}); denied(root, outside);
            denied(root, root.resolve("missing.png"));
            denied(root, Files.write(root.resolve("empty.png"), new byte[0]));
            denied(root, Files.write(root.resolve("secret.txt"), new byte[]{1}));
            Path nested = Files.createDirectory(root.resolve("nested"));
            denied(root, Files.write(nested.resolve("capture.png"), new byte[]{1}));
            denied(root, root.resolve("./capture.PNG"));
            denied(root, root.resolve("../Snapshots/capture.PNG"));
            denied(root, Files.createSymbolicLink(root.resolve("external.png"), outside));
            denied(root, Files.createSymbolicLink(root.resolve("alias.png"), image));
            Path rootAlias = Files.createSymbolicLink(temporary.resolve("alias-root"), root); denied(rootAlias, image);
            Path large = root.resolve("large.png");
            try (RandomAccessFile file = new RandomAccessFile(large.toFile(), "rw")) { file.setLength(SnapshotFilePolicy.MAX_BYTES + 1); }
            denied(root, large);
            Object owner = new Object(), replacement = new Object();
            SnapshotLease request = new SnapshotLease(1, 2, 3, owner);
            check(request.accepts(1, 2, 3, owner));
            check(!request.accepts(2, 2, 3, owner) && !request.accepts(1, 9, 3, owner));
            check(!request.accepts(1, 2, 4, owner) && !request.accepts(1, 2, 3, replacement));
            check(!request.close(1, 2, 4, owner)); check(request.close(1, 2, 3, owner));
            check(!request.cancelled()); // A successful completion must not delete a published image.
            check(!request.accepts(1, 2, 3, owner) && !request.close(1, 2, 3, owner));
            request = new SnapshotLease(1, 4, 5, replacement);
            check(request.abort(1, 4, 5, replacement) && request.cancelled());
            check(!request.accepts(1, 4, 5, replacement));
        } finally {
            try (java.util.stream.Stream<Path> paths = Files.walk(temporary)) {
                paths.sorted(Comparator.reverseOrder()).forEach(path -> { try { Files.delete(path); } catch (IOException failure) { throw new RuntimeException(failure); } });
            }
        }
        System.out.println("PASS: canonical snapshot root, bounded image files, symlinks and immutable callback leases");
    }
}
