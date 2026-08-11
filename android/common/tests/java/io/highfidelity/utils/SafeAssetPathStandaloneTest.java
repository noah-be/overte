package io.highfidelity.utils;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;

public final class SafeAssetPathStandaloneTest {
    private static int assertions;

    public static void main(String[] arguments) throws Exception {
        File parent = Files.createTempDirectory("overte-safe-assets").toFile();
        File root = new File(parent, "cache");
        root.mkdirs();
        expectPath(new File(root, "qml/file.qml"), SafeAssetPath.resolve(root, "qml/file.qml"));
        expectPath(new File(root, "safe.qml"), SafeAssetPath.resolve(root, "qml/../safe.qml"));
        reject(null, "file.qml");
        reject(root, null);
        reject(root, "");
        reject(root, "../escape");
        reject(root, new File(parent, "absolute-escape").getAbsolutePath());
        reject(root, "../cache-evil/payload");
        reject(root, "control-\u0001-path");
        File outside = new File(parent, "outside");
        outside.mkdirs();
        Files.createSymbolicLink(new File(root, "link").toPath(), outside.toPath());
        reject(root, "link/payload");
        expectPath(new File(File.separator, "tmp"),
                SafeAssetPath.resolve(new File(File.separator), "tmp"));
        reject(new File(File.separator), ".");
        deterministicPropertyChecks(root);
        System.out.println("SafeAssetPathStandaloneTest: " + assertions + " assertions passed");
    }

    private static void deterministicPropertyChecks(File root) throws Exception {
        long state = 0x5341464550415448L;
        String alphabet = "abcdefghijklmnopqrstuvwxyz0123456789_-";
        for (int caseIndex = 0; caseIndex < 256; ++caseIndex) {
            StringBuilder path = new StringBuilder("generated/");
            int length = 1 + (int) (state & 31);
            for (int index = 0; index < length; ++index) {
                state = state * 2862933555777941757L + 3037000493L;
                path.append(alphabet.charAt((int) ((state >>> 1) % alphabet.length())));
            }
            expectPath(new File(root, path.toString()), SafeAssetPath.resolve(root, path.toString()));
            reject(root, "generated/" + path + "/../../../../escape-" + caseIndex);
        }
    }

    private static void reject(File root, String value) throws Exception {
        ++assertions;
        try {
            SafeAssetPath.resolve(root, value);
            throw new AssertionError("accepted unsafe path: " + value);
        } catch (IOException expected) {
            // Expected.
        }
    }

    private static void expectPath(File expected, File actual) throws Exception {
        ++assertions;
        if (!expected.getCanonicalFile().equals(actual)) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }
}
