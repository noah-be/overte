package org.overte.phone;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;

import org.qtproject.qt5.android.bindings.QtActivity;

import io.highfidelity.utils.HifiUtils;

/** Hosts Overte's existing mono 2D display and touchscreen input plugins. */
public final class PhoneInterfaceActivity extends QtActivity {
    private static final int IMMERSIVE_UI_FLAGS =
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE;

    private static native void nativeProcessUrl(String url);

    @Override
    public void onCreate(Bundle savedInstanceState) {
        String requestedParameters = getIntent().getStringExtra("applicationArguments");
        if (requestedParameters == null) {
            requestedParameters = "";
        }
        APPLICATION_PARAMETERS = requestedParameters + " --cache "
            + getCacheDir().getAbsolutePath();

        HifiUtils.upackAssets(getAssets(), getCacheDir().getAbsolutePath());
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        applyImmersiveMode();
    }

    @Override
    protected void onResume() {
        super.onResume();
        applyImmersiveMode();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        Uri destination = intent.getData();
        if (destination != null && isOverteScheme(destination.getScheme())) {
            nativeProcessUrl(destination.toString());
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            applyImmersiveMode();
        }
    }

    @SuppressWarnings("deprecation")
    private void applyImmersiveMode() {
        // Qt 5 still lays out its surface using the legacy decor-view API.
        // Reapplying it after focus changes also hides bars exposed by the IME.
        getWindow().getDecorView().setSystemUiVisibility(IMMERSIVE_UI_FLAGS);
    }

    private static boolean isOverteScheme(String scheme) {
        return "overte".equalsIgnoreCase(scheme)
                || "hifi".equalsIgnoreCase(scheme);
    }
}
