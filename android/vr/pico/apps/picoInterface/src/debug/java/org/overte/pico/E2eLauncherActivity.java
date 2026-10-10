// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

import android.app.Activity;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import org.overte.e2e.E2eLauncherActivityBase;

/** Shell-only entry point; this class does not exist in release APKs. */
public final class E2eLauncherActivity extends E2eLauncherActivityBase {
    @Override
    protected void prepareAdditionalAssets(File directory) throws IOException {
        copyAsset("scripted_interactable.js", directory);
        copyAsset("ControlledTextInput.qml", directory);
        // This APK-owned fixture script uses the existing immutable-resource
        // trust path. File/world scripts retain their normal consent checks.
        File scene = new File(directory, "scene.json");
        try {
            JSONObject contents = new JSONObject(new String(
                    Files.readAllBytes(scene.toPath()), StandardCharsets.UTF_8));
            JSONArray entities = contents.getJSONArray("Entities");
            int matches = 0;
            for (int index = 0; index < entities.length(); ++index) {
                JSONObject entity = entities.getJSONObject(index);
                if ("OVERTE_E2E_INTERACTABLE".equals(entity.optString("name"))) {
                    if (!"scripted_interactable.js".equals(entity.getString("script"))
                            || entity.getBoolean("locked")) {
                        throw new IOException("unexpected scripted fixture contract");
                    }
                    entity.put("script", "qrc:///overte-e2e/scripted_interactable.js");
                    ++matches;
                }
            }
            if (matches != 1) {
                throw new IOException("scripted fixture target must be unique");
            }
            File temporary = new File(directory, "scene.json.tmp");
            try (FileOutputStream output = new FileOutputStream(temporary, false)) {
                output.write(contents.toString().getBytes(StandardCharsets.UTF_8));
                output.getFD().sync();
            }
            if (!scene.delete() || !temporary.renameTo(scene)) {
                throw new IOException("could not commit scripted fixture URL");
            }
        } catch (JSONException exception) {
            throw new IOException("invalid scripted fixture scene", exception);
        }
    }

    @Override
    protected Class<? extends Activity> interfaceActivity() {
        return PicoInterfaceActivity.class;
    }
}
