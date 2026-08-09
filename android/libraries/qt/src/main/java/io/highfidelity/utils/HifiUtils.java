
package io.highfidelity.utils;

import android.content.res.AssetManager;

import java.io.IOException;

public class HifiUtils {

    public static void upackAssets(AssetManager assetManager, String destDir) {
        try {
            AssetCacheExtractor.unpack(assetManager::open, destDir);
        } catch (IOException e){
            throw new RuntimeException(e);
        }
    }
}
