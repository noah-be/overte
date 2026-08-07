package org.overte.phone;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;

/** Requests optional voice permission before starting the native client. */
public final class PermissionsActivity extends Activity {
    private static final int RECORD_AUDIO_REQUEST = 20;
    private static final String STATE_PENDING_URL = "pendingUrl";
    private static final String STATE_INTERFACE_LAUNCHED = "interfaceLaunched";
    private String pendingUrl;
    private boolean interfaceLaunched;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_startup);
        if (savedInstanceState == null) {
            pendingUrl = PhoneDeepLink.fromIntent(getIntent());
        } else {
            String savedUrl = savedInstanceState.getString(STATE_PENDING_URL);
            pendingUrl = savedUrl == null
                    ? null
                    : PhoneDeepLinkNormalizer.normalize(savedUrl);
            interfaceLaunched = savedInstanceState.getBoolean(STATE_INTERFACE_LAUNCHED);
        }

        if (interfaceLaunched) {
            // A recreated launcher must not start a second native activity.
            finish();
            return;
        }

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED) {
            launchInterface();
        } else {
            // A permission dialog does not provide a durable request token.
            // Request again after recreation instead of trusting a saved flag
            // that could strand this launcher after process restoration.
            requestPermissions(
                    new String[] { Manifest.permission.RECORD_AUDIO },
                    RECORD_AUDIO_REQUEST);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        // A newer intent supersedes any URL that arrived while permission UI
        // was active. Invalid and non-VIEW intents deliberately clear it.
        pendingUrl = PhoneDeepLink.fromIntent(intent);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        outState.putString(STATE_PENDING_URL, pendingUrl);
        outState.putBoolean(STATE_INTERFACE_LAUNCHED, interfaceLaunched);
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
        if (pendingUrl != null) {
            // PhoneInterfaceActivity is not exported and validates this value
            // again. Never place externally supplied text in Qt's argv.
            intent.putExtra(PhoneDeepLink.EXTRA_URL, pendingUrl);
        }
        startActivity(intent);
        finish();
    }

}
