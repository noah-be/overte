package org.overte.phone;

import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;

import org.qtproject.qt5.android.bindings.QtActivity;

import io.highfidelity.utils.HifiUtils;

/** Hosts Overte's existing mono 2D display and touchscreen input plugins. */
public final class PhoneInterfaceActivity extends QtActivity {
    static {
        // Match the OpenSSL 3 SONAMEs and Qt's Android _3 runtime lookup.
        // Load crypto before ssl, whose DT_NEEDED refers to libcrypto_3.so.
        System.loadLibrary("crypto_3");
        System.loadLibrary("ssl_3");
    }

    private static final int IMMERSIVE_UI_FLAGS =
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE;

    private static native boolean nativeProcessUrl(String url);
    private static native boolean nativeHandleBack();
    private static final long URL_RETRY_DELAY_MS = 100;
    private static final int MAX_URL_RETRY_ATTEMPTS = 300;
    private static final String STATE_PENDING_URL = "pendingUrl";
    private static final String STATE_PENDING_URL_RETRY_ATTEMPTS = "pendingUrlRetryAttempts";
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Runnable drainPendingUrlTask = this::drainPendingUrl;
    private String pendingUrl;
    private int pendingUrlRetryAttempts;
    private boolean resumed;
    private boolean nativeBackConsumed;
    private Object api33BackHandler;

    // Keep API-33-only types out of the Activity's field signatures so this
    // class remains verifiable on the supported Android 8-12 releases.
    private static final class Api33BackHandler {
        private final PhoneInterfaceActivity activity;
        private final OnBackInvokedCallback callback;

        Api33BackHandler(PhoneInterfaceActivity activity) {
            this.activity = activity;
            callback = activity::handleSystemBack;
            activity.getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT, callback);
        }

        void unregister() {
            activity.getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(callback);
        }
    }

    private boolean tryHandleNativeBack() {
        try {
            return nativeHandleBack();
        } catch (UnsatisfiedLinkError error) {
            return false;
        }
    }

    private void handleSystemBack() {
        if (!tryHandleNativeBack()) {
            // There is no remaining phone UI layer to close. Preserve the Qt
            // process and background the task instead of terminating native
            // state through Qt 5's legacy Back implementation.
            moveTaskToBack(true);
        }
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_BACK) {
            if (event.getAction() == KeyEvent.ACTION_DOWN) {
                if (event.getRepeatCount() == 0) {
                    nativeBackConsumed = tryHandleNativeBack();
                }
                // Once the first Down belongs to native/QML navigation, keep
                // the complete long-press gesture away from Qt until Key Up.
                if (nativeBackConsumed) {
                    return true;
                }
            } else if (event.getAction() == KeyEvent.ACTION_UP && nativeBackConsumed) {
                nativeBackConsumed = false;
                return true;
            }
        }
        return super.dispatchKeyEvent(event);
    }

    @Override
    public void onBackPressed() {
        // Qt 5 delegates some Android Back deliveries directly to this
        // callback without dispatching a KeyEvent to the Activity subclass.
        handleSystemBack();
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Establish the final phone orientation before Qt creates its surface.
        // Otherwise Qt 5 can retain the small portrait launch geometry after
        // Android rotates the Activity to landscape.
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);

        // QtActivityLoader appends its trusted applicationArguments extra. Do
        // not copy it into APPLICATION_PARAMETERS as that duplicates argv.
        APPLICATION_PARAMETERS = "--cache " + getCacheDir().getAbsolutePath();

        // Deep links use a dedicated internal extra, never Qt's command line.
        // Preserve an undelivered link across Activity recreation; still
        // consume the Intent extra so QtActivityLoader cannot retain it.
        String intentUrl = takePendingUrl(getIntent());
        if (savedInstanceState != null) {
            String savedUrl = PhoneDeepLinkNormalizer.normalize(
                    savedInstanceState.getString(STATE_PENDING_URL));
            pendingUrl = savedUrl != null ? savedUrl : intentUrl;
            pendingUrlRetryAttempts = savedUrl != null
                    ? Math.max(0, Math.min(MAX_URL_RETRY_ATTEMPTS - 1,
                            savedInstanceState.getInt(STATE_PENDING_URL_RETRY_ATTEMPTS)))
                    : 0;
        } else {
            replacePendingUrl(intentUrl);
        }

        HifiUtils.upackAssets(getAssets(), getCacheDir().getAbsolutePath());
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= 33) {
            api33BackHandler = new Api33BackHandler(this);
        }
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        applyPhoneWindowBounds();
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        applyPhoneWindowBounds();
        drainPendingUrl();
    }

    @Override
    protected void onPause() {
        resumed = false;
        // Android may pause the Activity before delivering the matching key-up
        // (for example after Back backgrounds the task). Never carry that
        // one-gesture bookkeeping into the next foreground session.
        nativeBackConsumed = false;
        mainHandler.removeCallbacks(drainPendingUrlTask);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        resumed = false;
        mainHandler.removeCallbacks(drainPendingUrlTask);
        if (Build.VERSION.SDK_INT >= 33 && api33BackHandler != null) {
            ((Api33BackHandler) api33BackHandler).unregister();
            api33BackHandler = null;
        }
        super.onDestroy();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        outState.putString(STATE_PENDING_URL, pendingUrl);
        outState.putInt(STATE_PENDING_URL_RETRY_ATTEMPTS, pendingUrlRetryAttempts);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        // singleTask delivers repeated links here. Keep only the latest valid
        // destination, and clear an older pending value on every newer intent.
        String destination = takePendingUrl(intent);
        replacePendingUrl(destination);
        drainPendingUrl();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            applyPhoneWindowBounds();
        }
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        applyPhoneWindowBounds();
    }

    private void applyPhoneWindowBounds() {
        Window window = getWindow();
        window.setLayout(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT);
        applyImmersiveMode();
    }


    @SuppressWarnings("deprecation")
    private void applyImmersiveMode() {
        Window window = getWindow();
        View decorView = window.getDecorView();

        // Drawing into display cutouts is supported from Android 9 onward.
        // SHORT_EDGES preserves the landscape viewport without relying on
        // newer cutout modes that do not exist on all supported devices.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            WindowManager.LayoutParams attributes = window.getAttributes();
            attributes.layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            window.setAttributes(attributes);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // Android 11+ owns edge-to-edge layout through WindowInsets. This
            // also avoids relying on deprecated flags under Android 15/16's
            // enforced edge-to-edge behavior.
            window.setDecorFitsSystemWindows(false);
            WindowInsetsController controller = decorView.getWindowInsetsController();
            if (controller != null) {
                controller.hide(WindowInsets.Type.systemBars());
                controller.setSystemBarsBehavior(
                        WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            // Qt 5 on API 26-29 still lays out its surface using the legacy
            // decor-view API. Reapply after focus changes and IME dismissal.
            decorView.setSystemUiVisibility(IMMERSIVE_UI_FLAGS);
        }
    }

    private String takePendingUrl(Intent intent) {
        String destination = PhoneDeepLink.fromInternalExtra(intent);
        if (intent != null) {
            intent.removeExtra(PhoneDeepLink.EXTRA_URL);
        }
        return destination;
    }

    private void drainPendingUrl() {
        mainHandler.removeCallbacks(drainPendingUrlTask);
        // onNewIntent may run while this singleTask Activity is backgrounded.
        // Retain the latest destination until onResume instead of navigating a
        // world behind another foreground application.
        if (!PhonePendingUrlPolicy.canAttempt(pendingUrl, resumed)) {
            return;
        }
        boolean handedOff = false;
        try {
            // Qt loads libphoneInterface as part of its asynchronous startup.
            handedOff = nativeProcessUrl(pendingUrl);
        } catch (UnsatisfiedLinkError nativeLibraryNotReady) {
            // Keep the latest URL pending until Qt has loaded the JNI symbol.
        }
        if (handedOff) {
            pendingUrl = null;
            pendingUrlRetryAttempts = 0;
        } else {
            ++pendingUrlRetryAttempts;
            if (PhonePendingUrlPolicy.afterFailedAttempt(
                    resumed, pendingUrlRetryAttempts, MAX_URL_RETRY_ATTEMPTS)
                    == PhonePendingUrlPolicy.FailedAttemptAction.RETRY) {
                // Qt's application object is created asynchronously by QtActivity.
                // Retain the latest URL and retry instead of losing an early intent.
                mainHandler.postDelayed(drainPendingUrlTask, URL_RETRY_DELAY_MS);
            } else {
                // Avoid an unbounded main-thread wakeup loop if native startup
                // fails permanently. A newer intent starts a fresh retry budget.
                pendingUrl = null;
                pendingUrlRetryAttempts = 0;
            }
        }
    }

    private void replacePendingUrl(String destination) {
        pendingUrl = destination;
        pendingUrlRetryAttempts = 0;
    }
}
