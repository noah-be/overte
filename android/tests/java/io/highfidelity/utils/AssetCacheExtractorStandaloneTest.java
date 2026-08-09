package io.highfidelity.utils;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.HashMap;
import java.util.Map;

public final class AssetCacheExtractorStandaloneTest {
    public static void main(String[] args) throws Exception {
        File root = Files.createTempDirectory("asset-extractor").toFile();
        try {
            Source source = new Source("123\nnested/a.txt\nbinary\n");
            source.put("nested/a.txt", "fresh");
            source.put("binary", new byte[] { 0, (byte) 255 });
            unpackSuccessfully(source, root);
            check("fresh".equals(new String(
                    Files.readAllBytes(new File(root, "nested/a.txt").toPath()),
                    StandardCharsets.UTF_8)));
            check(Files.readAllBytes(new File(root, "binary").toPath())[1] == (byte) 255);
            check(new File(root, "123").isFile());

            Source hit = new Source("123\nmissing.txt\n");
            unpackSuccessfully(hit, root);
            check(hit.opens == 1);

            Files.write(new File(root, "stale").toPath(), "long-stale".getBytes(StandardCharsets.UTF_8));
            Source stale = new Source("456\nstale\n");
            stale.put("stale", "new");
            unpackSuccessfully(stale, root);
            check(Files.readAllBytes(new File(root, "stale").toPath()).length == 3);

            File staleDirectory = new File(root, "stale-directory");
            check(staleDirectory.mkdir());
            Source replaceDirectory = new Source("457\nstale-directory\nnew/parent/file\n");
            replaceDirectory.put("stale-directory", "now-a-file");
            replaceDirectory.put("new/parent/file", "nested");
            unpackSuccessfully(replaceDirectory, root);
            check(new File(root, "stale-directory").isFile());
            check(new File(root, "new/parent/file").isFile());

            expectMarkerFailure(new Source(""), root);
            expectMarkerFailure(new Source("bad marker\nasset\n"), root);
            expectMarkerFailure(new Source("184467440737095516160\nasset\n"), root);
            Source traversal = new Source("789\n../escape\n");
            traversal.put("../escape", "bad");
            expectFailure(traversal, root);
            check(!new File(root.getParentFile(), "escape").exists());

            Source partial = new Source("999\nfirst\nmissing\n");
            partial.put("first", "ok");
            expectFailure(partial, root);
            check(new File(root, "first").isFile());
            check(!new File(root, "999").exists());
            check(partial.closes == 2);

            Source unicodeDuplicate = new Source("1002\nüñîçødé/file\nüñîçødé/file\n");
            unicodeDuplicate.put("üñîçødé/file", "unicode");
            unpackSuccessfully(unicodeDuplicate, root);
            check(unicodeDuplicate.opens == 3);
            check(new File(root, "üñîçødé/file").isFile());

            for (String unsafe : new String[] {
                    new File(root, "absolute").getAbsolutePath(), "control-\u0001-name",
                    repeat('a', 8192)
            }) {
                Source unsafeSource = new Source("1003\n" + unsafe + "\n");
                unsafeSource.put(unsafe, "bad");
                expectFailure(unsafeSource, root);
                check(!new File(root, "1003").exists());
            }

            File markerCollision = new File(root, "1004");
            check(markerCollision.mkdir());
            Source collision = new Source("1004\npayload\n");
            collision.put("payload", "bad");
            expectFailure(collision, root);
            check(!new File(root, "payload").exists());

            File missingRoot = new File(root, "missing-root");
            Source missingDestination = new Source("1005\nnested/payload\n");
            missingDestination.put("nested/payload", "bad");
            expectFailure(missingDestination, missingRoot);
            check(!missingRoot.exists());

            File outside = Files.createTempDirectory("asset-outside").toFile();
            File link = new File(root, "outside-link");
            try {
                Files.createSymbolicLink(link.toPath(), outside.toPath());
                Source symlink = new Source("1006\noutside-link/payload\n");
                symlink.put("outside-link/payload", "bad");
                expectFailure(symlink, root);
                check(!new File(outside, "payload").exists());
            } finally {
                Files.deleteIfExists(link.toPath());
                deleteTree(outside, outside);
            }

            Source zeroRead = new Source("1007\nzero-read\n");
            zeroRead.put("zero-read", "complete");
            zeroRead.zeroReadAsset = "zero-read";
            unpackSuccessfully(zeroRead, root);
            check("complete".equals(new String(
                    Files.readAllBytes(new File(root, "zero-read").toPath()),
                    StandardCharsets.UTF_8)));
            check(zeroRead.closes == 2);

            Source closeFailure = new Source("1008\nclose-failure\n");
            closeFailure.put("close-failure", "copied-before-close");
            closeFailure.closeFailureAsset = "close-failure";
            expectFailure(closeFailure, root);
            check(closeFailure.closes == 2);
            check(!new File(root, "1008").exists());

            File rootFile = new File(root, "not-a-directory");
            check(rootFile.createNewFile());
            Source blockedRoot = new Source("1000\nnested/asset\n");
            blockedRoot.put("nested/asset", "x");
            expectFailure(blockedRoot, rootFile);

            File blockingAncestor = new File(root, "blocking-ancestor");
            check(blockingAncestor.createNewFile());
            Source blockedParent = new Source("1010\nblocking-ancestor/nested/asset\n");
            blockedParent.put("blocking-ancestor/nested/asset", "x");
            expectFailure(blockedParent, root);
            check(!new File(root, "1010").exists());

            File occupied = new File(root, "occupied");
            check(occupied.mkdir());
            check(new File(occupied, "child").createNewFile());
            Source cannotReplace = new Source("1001\noccupied\n");
            cannotReplace.put("occupied", "x");
            expectFailure(cannotReplace, root);
            System.out.println("AssetCacheExtractorStandaloneTest: marker, cache-hit, parent, stale, copy-failure and no-marker cases passed");
        } finally {
            deleteTree(root, root);
        }
    }

    private static void expectFailure(Source source, File root) throws Exception {
        try {
            AssetCacheExtractor.unpack(source, root.getPath());
            throw new AssertionError("expected IOException");
        } catch (IOException expected) {
            // expected
        }
    }

    private static void unpackSuccessfully(Source source, File root) {
        try {
            AssetCacheExtractor.unpack(source, root.getPath());
        } catch (IOException error) {
            throw new AssertionError("unexpected extraction failure", error);
        }
    }

    private static void expectMarkerFailure(Source source, File root) throws Exception {
        try {
            AssetCacheExtractor.unpack(source, root.getPath());
            throw new AssertionError("expected marker validation failure");
        } catch (IOException expected) {
            if (!"Invalid packaged asset cache marker".equals(expected.getMessage())) {
                throw new AssertionError("wrong marker failure", expected);
            }
        }
    }

    private static void check(boolean value) {
        if (!value) throw new AssertionError("assertion failed");
    }

    private static String repeat(char value, int count) {
        StringBuilder result = new StringBuilder(count);
        for (int index = 0; index < count; ++index) result.append(value);
        return result.toString();
    }

    private static void deleteTree(File root, File file) throws IOException {
        String rootPath = root.getCanonicalPath();
        String filePath = file.getCanonicalPath();
        if (!filePath.equals(rootPath) && !filePath.startsWith(rootPath + File.separator)) {
            throw new IOException("refusing cleanup outside test root");
        }
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) deleteTree(root, child);
        }
        if (!file.delete() && file.exists()) throw new IOException("test cleanup failed");
    }

    private static final class Source implements AssetCacheExtractor.Source {
        final Map<String, byte[]> values = new HashMap<>();
        int opens;
        int closes;
        String zeroReadAsset;
        String closeFailureAsset;
        Source(String manifest) { put("cache_assets.txt", manifest); }
        void put(String path, String value) { values.put(path, value.getBytes(StandardCharsets.UTF_8)); }
        void put(String path, byte[] value) { values.put(path, value); }
        public ByteArrayInputStream open(String path) throws IOException {
            ++opens;
            byte[] value = values.get(path);
            if (value == null) throw new IOException("missing fixture");
            return new ByteArrayInputStream(value) {
                boolean returnedZero;
                @Override
                public synchronized int read(byte[] buffer, int offset, int length) {
                    if (path.equals(zeroReadAsset) && !returnedZero) {
                        returnedZero = true;
                        return 0;
                    }
                    return super.read(buffer, offset, length);
                }
                @Override
                public void close() throws IOException {
                    ++closes;
                    super.close();
                    if (path.equals(closeFailureAsset)) throw new IOException("close failure fixture");
                }
            };
        }
    }
}
