// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.e2e;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/** Debug-source-set-only launcher for the fixed, repository-owned E2E assets. */
public abstract class E2eLauncherActivityBase extends Activity {
    private static final String TAG = "OverteE2E";
    private static final String DIRECTORY = "overte-e2e";
    private static final String PROBE_ASSET = "overte_e2e_probe.js";
    private static final String SCENE_ASSET = "scene.json";
    private static final String CONTROL_MARKER = "android-control.json";
    private static final String CONTROL_COMMAND = "android-control-command.json";
    private static final String CONTROL_CONTRACT =
            "{\"channel\":\"android-debug-file-v1\",\"probe\":\"overte_e2e_probe.js\","
                    + "\"schemaVersion\":1}\n";
    private static final String EMPTY_CONTROL_COMMAND = "{\"schemaVersion\":1}\n";
    // AddressManager applies viewpoint coordinates to the avatar body. Start
    // safely above the floor and let the character controller settle the
    // canonical feet position onto y=0 before the probe accepts the fixture.
    private static final String SPAWN_VIEWPOINT = "/0,2,4/0,0,0,1";

    protected abstract Class<? extends Activity> interfaceActivity();

    @Override
    protected final void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            File launchDirectory = new File(getFilesDir(), DIRECTORY);
            requireDirectory(launchDirectory);

            File probe = copyAsset(PROBE_ASSET, launchDirectory);
            File scene = copyAsset(SCENE_ASSET, launchDirectory);
            writeAtomically(CONTROL_MARKER, CONTROL_CONTRACT, launchDirectory);
            writeAtomically(CONTROL_COMMAND, EMPTY_CONTROL_COMMAND, launchDirectory);
            File previousProbe = new File(launchDirectory, "overte-probe.json");
            deleteIfPresent(previousProbe, "previous probe snapshot");

            Uri sceneUrl = Uri.fromFile(scene).buildUpon()
                    .appendQueryParameter("location", SPAWN_VIEWPOINT)
                    .build();
            String arguments = "--url " + sceneUrl
                    + " --testScript " + probe.getAbsolutePath()
                    + " --testResultsLocation " + launchDirectory.getAbsolutePath()
                    + " --no-login-suggestion";
            Intent intent = new Intent(this, interfaceActivity());
            intent.putExtra("applicationArguments", arguments);
            startActivity(intent);
        } catch (IOException | RuntimeException exception) {
            Log.e(TAG, "E2E launch preparation failed", exception);
        } finally {
            finish();
        }
    }

    private static void requireDirectory(File directory) throws IOException {
        if (directory == null || (!directory.isDirectory() && !directory.mkdirs())) {
            throw new IOException("could not create E2E directory");
        }
    }

    private File copyAsset(String name, File directory) throws IOException {
        File destination = new File(directory, name);
        File temporary = new File(directory, name + ".tmp");
        try (InputStream input = getAssets().open(name);
             FileOutputStream output = new FileOutputStream(temporary, false)) {
            byte[] buffer = new byte[8192];
            int length;
            while ((length = input.read(buffer)) != -1) {
                output.write(buffer, 0, length);
            }
            output.getFD().sync();
        }
        if (destination.exists() && !destination.delete()) {
            throw new IOException("could not replace E2E asset");
        }
        if (!temporary.renameTo(destination)) {
            throw new IOException("could not commit E2E asset");
        }
        return destination;
    }

    private static File writeAtomically(String name, String value, File directory)
            throws IOException {
        File destination = new File(directory, name);
        File temporary = new File(directory, name + ".tmp");
        try (FileOutputStream output = new FileOutputStream(temporary, false)) {
            output.write(value.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
        if (destination.exists() && !destination.delete()) {
            throw new IOException("could not replace E2E control marker");
        }
        if (!temporary.renameTo(destination)) {
            throw new IOException("could not commit E2E control marker");
        }
        return destination;
    }

    private static void deleteIfPresent(File file, String label) throws IOException {
        if (file.exists() && !file.delete()) {
            throw new IOException("could not remove " + label);
        }
    }
}
