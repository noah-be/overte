package io.highfidelity.utils;

import java.io.File;
import java.io.IOException;

/** Canonical containment policy for assets extracted into application-private storage. */
final class SafeAssetPath {
    private SafeAssetPath() {
    }

    static File resolve(File destinationRoot, String relativePath) throws IOException {
        if (destinationRoot == null) {
            throw new IOException("Missing packaged asset destination root");
        }
        if (relativePath == null || relativePath.isEmpty()) {
            throw new IOException("Empty packaged asset destination");
        }
        for (int index = 0; index < relativePath.length(); ++index) {
            if (Character.isISOControl(relativePath.charAt(index))) {
                throw new IOException("Control character in packaged asset destination");
            }
        }
        if (new File(relativePath).isAbsolute()) {
            throw new IOException("Absolute packaged asset destination");
        }
        File canonicalRoot = destinationRoot.getCanonicalFile();
        File destination = new File(canonicalRoot, relativePath).getCanonicalFile();
        String rootPrefix = canonicalRoot.getPath();
        if (!rootPrefix.endsWith(File.separator)) {
            rootPrefix += File.separator;
        }
        if (destination.equals(canonicalRoot) || !destination.getPath().startsWith(rootPrefix)) {
            throw new IOException("Packaged asset destination escapes the application cache");
        }
        return destination;
    }
}
