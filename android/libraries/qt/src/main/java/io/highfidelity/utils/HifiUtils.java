
package io.highfidelity.utils;

import android.content.res.AssetManager;

import com.google.common.io.ByteStreams;
import com.google.common.io.Files;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.util.LinkedList;

public class HifiUtils {

    private static LinkedList<String> readAssetLines(AssetManager assetManager, String asset) throws IOException {
        LinkedList<String> assets = new LinkedList<>();
        InputStream is = assetManager.open(asset);
        BufferedReader in = new BufferedReader(new InputStreamReader(is, "UTF-8"));
        String line;
        while ((line=in.readLine()) != null) {
            assets.add(line);
        }
        in.close();
        return assets;
    }

    private static void copyAsset(AssetManager assetManager, String asset, String destFileName) throws IOException {
        try (InputStream is = assetManager.open(asset)) {
            try (OutputStream os = Files.asByteSink(new File(destFileName)).openStream()) {
                ByteStreams.copy(is, os);
            }
        }
    }

    public static void upackAssets(AssetManager assetManager, String destDir) {
        try {
            File destinationRoot = new File(destDir).getCanonicalFile();
            LinkedList<String> assets = readAssetLines(assetManager, "cache_assets.txt");
            String cacheStamp = assets.poll();
            if (cacheStamp == null ||
                    !cacheStamp.matches("(?:[0-9]{1,19}|[0-9a-f]{64})")) {
                throw new IOException("Invalid packaged asset cache marker");
            }
            File cacheStampFile = SafeAssetPath.resolve(destinationRoot, cacheStamp);
            if (cacheStampFile.exists()) {
                return;
            }
            for (String fileToCopy : assets) {
                File destFile = SafeAssetPath.resolve(destinationRoot, fileToCopy);
                {
                    File destFolder = destFile.getParentFile();
                    if (!destFolder.exists()) {
                        destFolder.mkdirs();
                    }
                    if (destFile.exists()) {
                        destFile.delete();
                    }
                }
                copyAsset(assetManager, fileToCopy, destFile.getPath());
            }
            Files.write("touch".getBytes(), cacheStampFile);
        } catch (IOException e){
            throw new RuntimeException(e);
        }
    }
}
