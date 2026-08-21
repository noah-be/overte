package org.overte.phone;

import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.graphics.Insets;
import android.hardware.input.InputManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Vibrator;
import android.view.DisplayCutout;
import android.view.InputDevice;
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
public final class PhoneInterfaceActivity extends QtActivity
        implements InputManager.InputDeviceListener {
    static {
        // The packaged filenames must end in .so, while OpenSSL 1.1 keeps its
        // versioned SONAME. Loading both libraries first registers those
        // SONAMEs before Android resolves libphoneInterface's dependencies.
        System.loadLibrary("crypto");
        System.loadLibrary("ssl");
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
    private static native boolean nativeUpdateTouchUiMetrics(
            int surfaceWidth,
            int surfaceHeight,
            int safeInsetLeft,
            int safeInsetTop,
            int safeInsetRight,
            int safeInsetBottom,
            int imeInsetBottom,
            float density,
            float fontScale,
            float contentScale,
            boolean keyboardVisible,
            boolean hoverSupported,
            boolean hardwareKeyboardSupported,
            boolean hapticsSupported);
    private static final long URL_RETRY_DELAY_MS = 100;
    private static final int MAX_URL_RETRY_ATTEMPTS = 300;
    private static final long METRICS_RETRY_DELAY_MS = 100;
    private static final int MAX_METRICS_RETRY_ATTEMPTS = 300;
    private static final String STATE_PENDING_URL = "pendingUrl";
    private static final String STATE_PENDING_URL_RETRY_ATTEMPTS = "pendingUrlRetryAttempts";
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Runnable drainPendingUrlTask = this::drainPendingUrl;
    private final Runnable drainTouchUiMetricsTask = this::drainTouchUiMetrics;
    private final View.OnLayoutChangeListener touchUiLayoutListener =
            (view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) ->
                    captureTouchUiMetrics();
    private String pendingUrl;
    private int pendingUrlRetryAttempts;
    private boolean resumed;
    private boolean nativeBackConsumed;
    private Object api33BackHandler;
    private PhoneTouchUiMetricsPolicy.Snapshot pendingTouchUiMetrics;
    private PhoneTouchUiMetricsPolicy.Snapshot lastPublishedTouchUiMetrics;
    private int touchUiMetricsRetryAttempts;
    private InputManager inputManager;
    private boolean inputListenerRegistered;

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
        // Establish adaptive sensor rotation before Qt creates its surface.
        // Otherwise Qt 5 can retain the previous orientation's launch geometry
        // after Android rotates the Activity.
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR);

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
        installTouchUiMetricsObserver();
        applyPhoneWindowBounds();
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        registerInputDeviceListener();
        applyPhoneWindowBounds();
        captureTouchUiMetrics();
        drainTouchUiMetrics();
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
        mainHandler.removeCallbacks(drainTouchUiMetricsTask);
        unregisterInputDeviceListener();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        resumed = false;
        mainHandler.removeCallbacks(drainPendingUrlTask);
        mainHandler.removeCallbacks(drainTouchUiMetricsTask);
        uninstallTouchUiMetricsObserver();
        unregisterInputDeviceListener();
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
            captureTouchUiMetrics();
        }
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        applyPhoneWindowBounds();
        captureTouchUiMetrics();
    }

    private void applyPhoneWindowBounds() {
        Window window = getWindow();
        window.setLayout(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT);
        applyImmersiveMode();
        window.getDecorView().requestApplyInsets();
    }

    private void installTouchUiMetricsObserver() {
        View decorView = getWindow().getDecorView();
        decorView.setOnApplyWindowInsetsListener((view, insets) -> {
            captureTouchUiMetrics(view, insets);
            return insets;
        });
        decorView.addOnLayoutChangeListener(touchUiLayoutListener);
        inputManager = (InputManager) getSystemService(INPUT_SERVICE);
        decorView.requestApplyInsets();
    }

    private void uninstallTouchUiMetricsObserver() {
        Window window = getWindow();
        if (window == null) {
            return;
        }
        View decorView = window.getDecorView();
        decorView.setOnApplyWindowInsetsListener(null);
        decorView.removeOnLayoutChangeListener(touchUiLayoutListener);
    }

    private void registerInputDeviceListener() {
        if (inputManager != null && !inputListenerRegistered) {
            inputManager.registerInputDeviceListener(this, mainHandler);
            inputListenerRegistered = true;
        }
    }

    private void unregisterInputDeviceListener() {
        if (inputManager != null && inputListenerRegistered) {
            inputManager.unregisterInputDeviceListener(this);
            inputListenerRegistered = false;
        }
    }

    @Override
    public void onInputDeviceAdded(int deviceId) {
        captureTouchUiMetrics();
    }

    @Override
    public void onInputDeviceRemoved(int deviceId) {
        captureTouchUiMetrics();
    }

    @Override
    public void onInputDeviceChanged(int deviceId) {
        captureTouchUiMetrics();
    }

    private void captureTouchUiMetrics() {
        View decorView = getWindow().getDecorView();
        captureTouchUiMetrics(decorView, decorView.getRootWindowInsets());
    }

    @SuppressWarnings("deprecation")
    private void captureTouchUiMetrics(View decorView, WindowInsets windowInsets) {
        int width = decorView.getWidth();
        int height = decorView.getHeight();
        if (width <= 0 || height <= 0) {
            return;
        }

        int left = 0;
        int top = 0;
        int right = 0;
        int bottom = 0;
        int imeBottom = 0;
        if (windowInsets != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Insets protectedInsets = windowInsets.getInsets(
                    WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            Insets mandatoryGestures = windowInsets.getInsets(
                    WindowInsets.Type.mandatorySystemGestures());
            Insets ime = windowInsets.getInsets(WindowInsets.Type.ime());
            left = Math.max(protectedInsets.left, mandatoryGestures.left);
            top = Math.max(protectedInsets.top, mandatoryGestures.top);
            right = Math.max(protectedInsets.right, mandatoryGestures.right);
            bottom = Math.max(protectedInsets.bottom, mandatoryGestures.bottom);
            imeBottom = ime.bottom;
        } else if (windowInsets != null) {
            int mandatoryLeft = 0;
            int mandatoryTop = 0;
            int mandatoryRight = 0;
            int mandatoryBottom = 0;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                Insets mandatoryGestures = windowInsets.getMandatorySystemGestureInsets();
                mandatoryLeft = mandatoryGestures.left;
                mandatoryTop = mandatoryGestures.top;
                mandatoryRight = mandatoryGestures.right;
                mandatoryBottom = mandatoryGestures.bottom;
            }
            int cutoutLeft = 0;
            int cutoutTop = 0;
            int cutoutRight = 0;
            int cutoutBottom = 0;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                DisplayCutout cutout = windowInsets.getDisplayCutout();
                if (cutout != null) {
                    cutoutLeft = cutout.getSafeInsetLeft();
                    cutoutTop = cutout.getSafeInsetTop();
                    cutoutRight = cutout.getSafeInsetRight();
                    cutoutBottom = cutout.getSafeInsetBottom();
                }
            }
            PhoneTouchUiMetricsPolicy.LegacyInsets legacyInsets =
                    PhoneTouchUiMetricsPolicy.normalizeLegacyInsets(
                            windowInsets.getSystemWindowInsetLeft(),
                            windowInsets.getSystemWindowInsetTop(),
                            windowInsets.getSystemWindowInsetRight(),
                            windowInsets.getSystemWindowInsetBottom(),
                            windowInsets.getStableInsetBottom(),
                            mandatoryLeft,
                            mandatoryTop,
                            mandatoryRight,
                            mandatoryBottom,
                            cutoutLeft,
                            cutoutTop,
                            cutoutRight,
                            cutoutBottom);
            left = legacyInsets.left;
            top = legacyInsets.top;
            right = legacyInsets.right;
            bottom = legacyInsets.bottom;
            imeBottom = legacyInsets.imeBottom;
        }

        Configuration configuration = getResources().getConfiguration();
        PhoneTouchUiMetricsPolicy.Snapshot snapshot = PhoneTouchUiMetricsPolicy.normalize(
                width,
                height,
                left,
                top,
                right,
                bottom,
                imeBottom,
                getResources().getDisplayMetrics().density,
                configuration.fontScale,
                hasHoverInput(),
                hasHardwareKeyboard(configuration),
                hasHaptics());
        if (!snapshot.valid || snapshot.equals(lastPublishedTouchUiMetrics)) {
            return;
        }
        if (!snapshot.equals(pendingTouchUiMetrics)) {
            pendingTouchUiMetrics = snapshot;
            touchUiMetricsRetryAttempts = 0;
        }
        drainTouchUiMetrics();
    }

    private boolean hasHoverInput() {
        for (int deviceId : InputDevice.getDeviceIds()) {
            InputDevice device = InputDevice.getDevice(deviceId);
            if (device != null && !device.isVirtual()
                    && (device.supportsSource(InputDevice.SOURCE_MOUSE)
                            || device.supportsSource(InputDevice.SOURCE_STYLUS))) {
                return true;
            }
        }
        return false;
    }

    private boolean hasHardwareKeyboard(Configuration configuration) {
        if (configuration.keyboard != Configuration.KEYBOARD_NOKEYS
                && configuration.hardKeyboardHidden
                        != Configuration.HARDKEYBOARDHIDDEN_YES) {
            return true;
        }
        for (int deviceId : InputDevice.getDeviceIds()) {
            InputDevice device = InputDevice.getDevice(deviceId);
            if (device != null && !device.isVirtual()
                    && device.getKeyboardType() == InputDevice.KEYBOARD_TYPE_ALPHABETIC) {
                return true;
            }
        }
        return false;
    }

    @SuppressWarnings("deprecation")
    private boolean hasHaptics() {
        Vibrator vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        return vibrator != null && vibrator.hasVibrator();
    }

    private void drainTouchUiMetrics() {
        mainHandler.removeCallbacks(drainTouchUiMetricsTask);
        if (!resumed || pendingTouchUiMetrics == null) {
            return;
        }
        PhoneTouchUiMetricsPolicy.Snapshot snapshot = pendingTouchUiMetrics;
        boolean accepted = false;
        try {
            accepted = nativeUpdateTouchUiMetrics(
                    snapshot.surfaceWidth,
                    snapshot.surfaceHeight,
                    snapshot.safeInsetLeft,
                    snapshot.safeInsetTop,
                    snapshot.safeInsetRight,
                    snapshot.safeInsetBottom,
                    snapshot.imeInsetBottom,
                    snapshot.density,
                    snapshot.fontScale,
                    snapshot.contentScale,
                    snapshot.keyboardVisible,
                    snapshot.hoverSupported,
                    snapshot.hardwareKeyboardSupported,
                    snapshot.hapticsSupported);
        } catch (UnsatisfiedLinkError nativeLibraryNotReady) {
            // Qt loads the phone native library asynchronously.
        }
        if (accepted) {
            lastPublishedTouchUiMetrics = snapshot;
            pendingTouchUiMetrics = null;
            touchUiMetricsRetryAttempts = 0;
            return;
        }

        ++touchUiMetricsRetryAttempts;
        if (touchUiMetricsRetryAttempts < MAX_METRICS_RETRY_ATTEMPTS) {
            mainHandler.postDelayed(drainTouchUiMetricsTask, METRICS_RETRY_DELAY_MS);
        } else {
            // A future layout, inset, configuration, or input-device change
            // starts a fresh bounded delivery attempt.
            pendingTouchUiMetrics = null;
            touchUiMetricsRetryAttempts = 0;
        }
    }


    @SuppressWarnings("deprecation")
    private void applyImmersiveMode() {
        Window window = getWindow();
        View decorView = window.getDecorView();

        // Drawing into display cutouts is supported from Android 9 onward.
        // SHORT_EDGES preserves the sensor-rotated viewport without relying on
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
