package io.highfidelity.questInterface;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.text.TextUtils;

public class PermissionsChecker extends Activity {
    private static final int REQUEST_PERMISSIONS = 20;
    private static final String[] REQUIRED_PERMISSIONS = new String[]{
        Manifest.permission.READ_EXTERNAL_STORAGE,
        Manifest.permission.WRITE_EXTERNAL_STORAGE,
        Manifest.permission.RECORD_AUDIO
    };

    private static final String EXTRA_ARGS = "args";
    private static final String STATE_INTERFACE_LAUNCHED = "interfaceLaunched";
    private String mArgs;
    private boolean interfaceLaunched;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        mArgs =(getIntent().getStringExtra(EXTRA_ARGS));
        interfaceLaunched = savedInstanceState != null
                && savedInstanceState.getBoolean(STATE_INTERFACE_LAUNCHED);

        if (interfaceLaunched) {
            finish();
            return;
        }

        requestAppPermissions(REQUIRED_PERMISSIONS,REQUEST_PERMISSIONS);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        outState.putBoolean(STATE_INTERFACE_LAUNCHED, interfaceLaunched);
        super.onSaveInstanceState(outState);
    }

    public void requestAppPermissions(final String[] requestedPermissions,
                                      final int requestCode) {
        int permissionCheck = PackageManager.PERMISSION_GRANTED;
        boolean shouldShowRequestPermissionRationale = false;
        for (String permission : requestedPermissions) {
            permissionCheck = permissionCheck + checkSelfPermission(permission);
            shouldShowRequestPermissionRationale = shouldShowRequestPermissionRationale || shouldShowRequestPermissionRationale(permission);
        }
        if (permissionCheck != PackageManager.PERMISSION_GRANTED) {
            System.out.println("Permission was not granted. Ask for permissions");
            if (shouldShowRequestPermissionRationale) {
                requestPermissions(requestedPermissions, requestCode);
            } else {
                requestPermissions(requestedPermissions, requestCode);
            }
        } else {
            System.out.println("Launching the other activity..");
            launchActivityWithPermissions();
        }
    }

    private void launchActivityWithPermissions() {
        if (interfaceLaunched) {
            return;
        }
        interfaceLaunched = true;
        Intent intent= new Intent(this, InterfaceActivity.class);

        if(!TextUtils.isEmpty(mArgs)) {
            intent.putExtra("applicationArguments", mArgs);
        }

        startActivity(intent);
        finish();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_PERMISSIONS) {
            return;
        }
        // These permissions affect optional input/storage features. As with an
        // explicit denial, Android may return an empty result when the request
        // is interrupted; neither case should strand the launcher Activity.
        launchActivityWithPermissions();
    }
}
