package io.highfidelity.utils;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedList;

/** Framework-independent implementation of the packaged Qt asset cache extraction. */
public final class AssetCacheExtractor {
    public interface Source {
        InputStream open(String asset) throws IOException;
    }

    private AssetCacheExtractor() {
    }

    public static void unpack(Source source, String destDir) throws IOException {
        File destinationRoot = new File(destDir).getCanonicalFile();
        if (!destinationRoot.isDirectory()) {
            throw new IOException("Packaged asset destination root is not a directory");
        }
        LinkedList<String> assets = readLines(source, "cache_assets.txt");
        String cacheStamp = assets.poll();
        if (cacheStamp == null || !cacheStamp.matches("(?:[0-9]{1,19}|[0-9a-f]{64})")) {
            throw new IOException("Invalid packaged asset cache marker");
        }
        File cacheStampFile = SafeAssetPath.resolve(destinationRoot, cacheStamp);
        if (cacheStampFile.isFile()) {
            return;
        }
        if (cacheStampFile.exists()) {
            throw new IOException("Packaged asset cache marker is not a file");
        }
        for (String asset : assets) {
            File destination = SafeAssetPath.resolve(destinationRoot, asset);
            File parent = destination.getParentFile();
            if (!parent.exists() && !parent.mkdirs() && !parent.isDirectory()) {
                throw new IOException("Could not create asset cache directory");
            }
            if (destination.exists() && !destination.delete()) {
                throw new IOException("Could not replace stale cached asset");
            }
            copy(source, asset, destination);
        }
        try (OutputStream output = new FileOutputStream(cacheStampFile)) {
            output.write("touch".getBytes(StandardCharsets.UTF_8));
        }
    }

    private static LinkedList<String> readLines(Source source, String asset) throws IOException {
        LinkedList<String> lines = new LinkedList<>();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                source.open(asset), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                lines.add(line);
            }
        }
        return lines;
    }

    private static void copy(Source source, String asset, File destination) throws IOException {
        try (InputStream input = source.open(asset);
                OutputStream output = new FileOutputStream(destination, false)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
        }
    }
}
