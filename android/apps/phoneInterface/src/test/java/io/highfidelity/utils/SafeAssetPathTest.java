package io.highfidelity.utils;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;

import org.junit.Test;

public final class SafeAssetPathTest {
    @Test
    public void resolvesNestedAndNormalizedPathsInsideRoot() throws Exception {
        File root = Files.createTempDirectory("overte-assets").toFile();
        assertEquals(new File(root, "qml/file.qml").getCanonicalFile(),
                SafeAssetPath.resolve(root, "qml/file.qml"));
        assertEquals(new File(root, "safe.qml").getCanonicalFile(),
                SafeAssetPath.resolve(root, "qml/../safe.qml"));
    }

    @Test
    public void rejectsEmptyMissingAbsoluteAndTraversingDestinations() throws Exception {
        File root = Files.createTempDirectory("overte-assets").toFile();
        assertThrows(IOException.class, () -> SafeAssetPath.resolve(null, "file"));
        assertThrows(IOException.class, () -> SafeAssetPath.resolve(root, null));
        assertThrows(IOException.class, () -> SafeAssetPath.resolve(root, ""));
        assertThrows(IOException.class, () -> SafeAssetPath.resolve(root, "../escape"));
        assertThrows(IOException.class, () -> SafeAssetPath.resolve(root, root.getParent() + "/escape"));
    }

    @Test
    public void siblingWithSharedPrefixIsNotTreatedAsDescendant() throws Exception {
        File parent = Files.createTempDirectory("overte-assets-parent").toFile();
        File root = new File(parent, "cache");
        File sibling = new File(parent, "cache-evil/payload");
        assertThrows(IOException.class, () -> SafeAssetPath.resolve(root,
                "../" + sibling.getParentFile().getName() + "/payload"));
    }

    @Test
    public void existingSymlinkCannotRedirectExtractionOutsideRoot() throws Exception {
        File parent = Files.createTempDirectory("overte-assets-parent").toFile();
        File root = new File(parent, "cache");
        File outside = new File(parent, "outside");
        root.mkdirs();
        outside.mkdirs();
        Files.createSymbolicLink(new File(root, "link").toPath(), outside.toPath());
        assertThrows(IOException.class, () -> SafeAssetPath.resolve(root, "link/payload"));
    }

    @Test
    public void containmentPolicyAlsoHandlesFilesystemRootCorrectly() throws Exception {
        File root = new File(File.separator);
        assertEquals(new File(root, "tmp").getCanonicalFile(),
                SafeAssetPath.resolve(root, "tmp"));
        assertThrows(IOException.class, () -> SafeAssetPath.resolve(root, "."));
    }
}
