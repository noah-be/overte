package org.overte.phone;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.text.TextUtils;

/** Requests optional voice permission before starting the native client. */
public final class PermissionsActivity extends Activity {
    private static final int RECORD_AUDIO_REQUEST = 20;
    private static final String STATE_LAUNCHED = "interfaceLaunched";
    private String applicationArguments;
    private boolean interfaceLaunched;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_startup);
        applicationArguments = getApplicationArguments(getIntent());
        interfaceLaunched = savedInstanceState != null
                && savedInstanceState.getBoolean(STATE_LAUNCHED, false);

        if (interfaceLaunched) {
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
        outState.putBoolean(STATE_LAUNCHED, interfaceLaunched);
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        String newArguments = getApplicationArguments(intent);
        if (!TextUtils.isEmpty(newArguments)) {
            applicationArguments = newArguments;
        }
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == RECORD_AUDIO_REQUEST) {
            // Voice remains optional; denying it must not block world access.
            launchInterface();
        }
    }

    private void launchInterface() {
        if (interfaceLaunched) {
            return;
        }
        interfaceLaunched = true;
        Intent intent = new Intent(this, PhoneInterfaceActivity.class);
        intent.setData(getIntent().getData());
        if (!TextUtils.isEmpty(applicationArguments)) {
            intent.putExtra("applicationArguments", applicationArguments);
        }
        startActivity(intent);
        finish();
    }

    private static String getApplicationArguments(Intent intent) {
        if (Intent.ACTION_VIEW.equals(intent.getAction())) {
            Uri destination = intent.getData();
            if (destination != null && isOverteScheme(destination.getScheme())) {
                return "--url " + destination.toString();
            }
        }
        return null;
    }

    private static boolean isOverteScheme(String scheme) {
        return "overte".equalsIgnoreCase(scheme)
                || "hifi".equalsIgnoreCase(scheme);
    }
}
