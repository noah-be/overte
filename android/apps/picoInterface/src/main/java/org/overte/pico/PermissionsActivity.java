package org.overte.pico;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;

public final class PermissionsActivity extends Activity {
    private static final int RECORD_AUDIO_REQUEST = 20;
    private static final String STATE_INTERFACE_LAUNCHED = "interfaceLaunched";
    private boolean interfaceLaunched;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_startup);
        interfaceLaunched = savedInstanceState != null
                && savedInstanceState.getBoolean(STATE_INTERFACE_LAUNCHED);

        if (interfaceLaunched) {
            finish();
            return;
        }

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED) {
            launchInterface();
        } else {
            requestPermissions(
                    new String[] { Manifest.permission.RECORD_AUDIO },
                    RECORD_AUDIO_REQUEST);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        outState.putBoolean(STATE_INTERFACE_LAUNCHED, interfaceLaunched);
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == RECORD_AUDIO_REQUEST) {
            // Voice is optional; Overte can still start if the user denies it.
            launchInterface();
        }
    }

    private void launchInterface() {
        if (interfaceLaunched) {
            return;
        }
        interfaceLaunched = true;
        Intent intent = new Intent(this, PicoInterfaceActivity.class);
        startActivity(intent);
        finish();
    }
}
