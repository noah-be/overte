package io.highfidelity.utils;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.HashMap;
import java.util.Map;

import org.junit.Test;
import org.junit.Rule;
import org.junit.rules.TemporaryFolder;

public final class AssetCacheExtractorTest {
    private static final String STAMP = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    @Rule
    public final TemporaryFolder temporary = new TemporaryFolder();

    @Test
    public void copiesNestedAssetsAndWritesMarkerLast() throws Exception {
        File root = temporary.newFolder("asset-cache");
        FakeSource source = source(STAMP + "\nqml/a.txt\nnative.bin\n");
        source.put("qml/a.txt", "hello");
        source.put("native.bin", new byte[] { 0, 1, (byte) 255 });

        AssetCacheExtractor.unpack(source, root.getPath());

        assertEquals("hello", new String(
                Files.readAllBytes(new File(root, "qml/a.txt").toPath()),
                StandardCharsets.UTF_8));
        assertArrayEquals(new byte[] { 0, 1, (byte) 255 },
                Files.readAllBytes(new File(root, "native.bin").toPath()));
        assertTrue(new File(root, STAMP).isFile());
    }

    @Test
    public void existingMarkerIsACacheHitAndDoesNotOpenPayloads() throws Exception {
        File root = temporary.newFolder("asset-cache-hit");
        assertTrue(new File(root, "42").createNewFile());
        FakeSource source = source("42\nmissing.txt\n");
        AssetCacheExtractor.unpack(source, root.getPath());
        assertEquals(1, source.opens);
        assertFalse(new File(root, "missing.txt").exists());
    }

    @Test
    public void stalePayloadIsTruncatedAndOverwritten() throws Exception {
        File root = temporary.newFolder("asset-cache-stale");
        File stale = new File(root, "value.txt");
        Files.write(stale.toPath(), "much-longer-stale-value".getBytes(StandardCharsets.UTF_8));
        FakeSource source = source("77\nvalue.txt\n");
        source.put("value.txt", "new");
        AssetCacheExtractor.unpack(source, root.getPath());
        assertEquals("new", new String(Files.readAllBytes(stale.toPath()), StandardCharsets.UTF_8));
    }

    @Test
    public void invalidMarkersAndTraversalFailClosed() throws Exception {
        File root = temporary.newFolder("asset-cache-invalid");
        for (String manifest : new String[] { "", "stamp with spaces\na.txt\n", "abc\n../escape\n" }) {
            try {
                FakeSource source = source(manifest);
                source.put("a.txt", "x");
                source.put("../escape", "x");
                AssetCacheExtractor.unpack(source, root.getPath());
                fail("expected invalid manifest to fail");
            } catch (IOException expected) {
                // Expected validation boundary.
            }
        }
        assertFalse(new File(root.getParentFile(), "escape").exists());
    }

    @Test
    public void partialFailureNeverPublishesSuccessMarker() throws Exception {
        File root = temporary.newFolder("asset-cache-partial");
        FakeSource source = source("99\nfirst.txt\nmissing.txt\n");
        source.put("first.txt", "copied");
        try {
            AssetCacheExtractor.unpack(source, root.getPath());
            fail("expected missing payload to fail");
        } catch (IOException expected) {
            assertTrue(new File(root, "first.txt").isFile());
            assertFalse(new File(root, "99").exists());
        }
    }

    @Test
    public void invalidDestinationShapesFailWithoutPublishingMarker() throws Exception {
        File root = temporary.newFolder("asset-cache-destination");
        File rootFile = new File(root, "not-a-directory");
        assertTrue(rootFile.createNewFile());
        FakeSource blockedRoot = source("1000\nnested/asset\n");
        blockedRoot.put("nested/asset", "x");
        expectFailure(blockedRoot, rootFile);

        File blockingAncestor = new File(root, "blocking-ancestor");
        assertTrue(blockingAncestor.createNewFile());
        FakeSource blockedParent = source("1010\nblocking-ancestor/nested/asset\n");
        blockedParent.put("blocking-ancestor/nested/asset", "x");
        expectFailure(blockedParent, root);

        File occupied = new File(root, "occupied");
        assertTrue(occupied.mkdir());
        assertTrue(new File(occupied, "child").createNewFile());
        FakeSource cannotReplace = source("1001\noccupied\n");
        cannotReplace.put("occupied", "x");
        expectFailure(cannotReplace, root);
        assertFalse(new File(root, "1001").exists());
    }

    @Test
    public void manifestEdgeCasesRemainContainedAndFailClosed() throws Exception {
        File root = temporary.newFolder("asset-cache-adversarial");
        FakeSource unicode = source("1002\nüñîçødé/file\nüñîçødé/file\n");
        unicode.put("üñîçødé/file", "ok");
        AssetCacheExtractor.unpack(unicode, root.getPath());
        assertEquals(3, unicode.opens);

        for (String unsafe : new String[] {
                new File(root, "absolute").getAbsolutePath(), "control-\u0001-name"
        }) {
            FakeSource source = source("1003\n" + unsafe + "\n");
            source.put(unsafe, "bad");
            expectFailure(source, root);
            assertFalse(new File(root, "1003").exists());
        }

        assertTrue(new File(root, "1004").mkdir());
        FakeSource markerCollision = source("1004\npayload\n");
        markerCollision.put("payload", "bad");
        expectFailure(markerCollision, root);
        assertFalse(new File(root, "payload").exists());

        File missingRoot = new File(root, "missing");
        FakeSource missingDestination = source("1005\nnested/payload\n");
        missingDestination.put("nested/payload", "bad");
        expectFailure(missingDestination, missingRoot);
        assertFalse(missingRoot.exists());
    }

    private static void expectFailure(FakeSource source, File root) throws Exception {
        try {
            AssetCacheExtractor.unpack(source, root.getPath());
            fail("expected extraction failure");
        } catch (IOException expected) {
            // Expected validation or filesystem failure.
        }
    }

    private static FakeSource source(String manifest) {
        FakeSource source = new FakeSource();
        source.put("cache_assets.txt", manifest);
        return source;
    }

    private static final class FakeSource implements AssetCacheExtractor.Source {
        private final Map<String, byte[]> assets = new HashMap<>();
        int opens;

        void put(String name, String value) {
            put(name, value.getBytes(StandardCharsets.UTF_8));
        }

        void put(String name, byte[] value) {
            assets.put(name, value);
        }

        @Override
        public ByteArrayInputStream open(String asset) throws IOException {
            ++opens;
            byte[] value = assets.get(asset);
            if (value == null) {
                throw new IOException("missing test asset");
            }
            return new ByteArrayInputStream(value);
        }
    }
}
