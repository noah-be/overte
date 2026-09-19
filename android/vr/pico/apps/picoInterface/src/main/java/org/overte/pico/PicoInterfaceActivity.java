package org.overte.pico;

import android.annotation.SuppressLint;
import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;
import org.overte.security.SafeDiagnostics.Event;
import android.view.KeyEvent;
import android.view.InputDevice;

import org.qtproject.qt5.android.bindings.QtActivity;

import io.highfidelity.utils.HifiUtils;

public final class PicoInterfaceActivity extends QtActivity {
    private static final PicoActivityInstancePolicy<PicoInterfaceActivity> INSTANCE =
        new PicoActivityInstancePolicy<>();
    private boolean resumed;

    static {
        // Shared emits canonical OpenSSL 3 filenames/SONAMEs. Preload crypto
        // before ssl and before QtNetwork initializes TLS; no renamed aliases.
        System.loadLibrary("crypto_3");
        System.loadLibrary("ssl_3");
        System.loadLibrary("picoOpenXR");
    }

    private native boolean initializeOpenXRLoader();
    private native boolean prepareProtectedAccountStore(PicoAccountStoreBridge peer);
    private native void releaseOpenXRActivity();

    static PicoInterfaceActivity getInstance() {
        return INSTANCE.current();
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        INSTANCE.register(this);
        runShutdownStep("Web input", () -> OffscreenWebView.setInputForeground(this, false));
        PicoClientVisibility.attach(this);
        APPLICATION_PARAMETERS = PicoInterfaceActivityPolicy.applicationParameters(
            getCacheDir().getAbsolutePath());

        HifiUtils.upackAssets(getAssets(), getCacheDir().getAbsolutePath());

        if (!initializeOpenXRLoader()) {
            RedactingDiagnostics.e(Event.REDACTED);
        }

        try {
            if (!prepareProtectedAccountStore(new PicoAccountStoreBridge(this))) {
                RedactingDiagnostics.e(Event.STORAGE_UNAVAILABLE);
            }
        } catch (RuntimeException error) {
            RedactingDiagnostics.e(Event.STORAGE_UNAVAILABLE);
        }
        super.onCreate(savedInstanceState);
        OffscreenWebView.initializeNativeBridge();
        AndroidAudioInput.initializeNativeBridge();
    }

    public static void scheduleRestart(String applicationArguments) {
        final PicoInterfaceActivity activity = INSTANCE.current();
        if (activity == null) {
            RedactingDiagnostics.e(Event.REDACTED);
            return;
        }
        if (!RestartArguments.store(activity, applicationArguments)) {
            RedactingDiagnostics.e(Event.CALLBACK_DISCARDED);
            return;
        }
        RedactingDiagnostics.i(Event.REDACTED);

        try {
            Intent restartIntent = new Intent(activity, RestartActivity.class);
            restartIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_CLEAR_TASK);

            PendingIntent pendingIntent = PendingIntent.getActivity(
                activity,
                1001,
                restartIntent,
                PendingIntent.FLAG_CANCEL_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            AlarmManager alarmManager =
                (AlarmManager) activity.getSystemService(Context.ALARM_SERVICE);
            if (alarmManager == null) {
                RedactingDiagnostics.e(Event.REDACTED);
                RestartArguments.clear(activity);
                return;
            }
            // Pico OS may batch inexact alarms as soon as the activity closes,
            // which leaves the application stopped instead of relaunching it.
            long restartAt = SystemClock.elapsedRealtime() + 1500;
            boolean canScheduleExactAlarms = Build.VERSION.SDK_INT < Build.VERSION_CODES.S
                    || alarmManager.canScheduleExactAlarms();
            if (PicoInterfaceActivityPolicy.canUseExactRestart(
                    Build.VERSION.SDK_INT, canScheduleExactAlarms)) {
                scheduleExactRestart(alarmManager, restartAt, pendingIntent);
            } else {
                alarmManager.setAndAllowWhileIdle(
                    AlarmManager.ELAPSED_REALTIME,
                    restartAt,
                    pendingIntent);
            }
        } catch (RuntimeException exception) {
            RedactingDiagnostics.e(Event.REDACTED);
            RestartArguments.clear(activity);
            return;
        }

        activity.finishAffinity();
        new android.os.Handler(activity.getMainLooper()).postDelayed(() -> {
            RedactingDiagnostics.i(Event.REDACTED);
            Process.killProcess(Process.myPid());
        }, 750);
    }

    @Override
    protected void onDestroy() {
        final boolean ownsLifecycle = INSTANCE.current() == this;
        if (ownsLifecycle) {
            runShutdownStep("Web input", () -> OffscreenWebView.setInputForeground(this, false));
        }
        PicoClientVisibility.detach(this);
        INSTANCE.clear(this);
        try {
            if (ownsLifecycle) {
                runShutdownStep("WebViews", OffscreenWebView::destroyAll);
                runShutdownStep("microphone", () -> AndroidAudioInput.setForeground(false));
            }
            runShutdownStep("OpenXR Activity", this::releaseOpenXRActivity);
        } finally {
            super.onDestroy();
        }
    }

    private static void runShutdownStep(String name, Runnable cleanup) {
        try {
            cleanup.run();
        } catch (RuntimeException | OutOfMemoryError exception) {
            RedactingDiagnostics.e(Event.REDACTED);
        }
    }

    @SuppressLint("MissingPermission")
    private static void scheduleExactRestart(
            AlarmManager alarmManager, long restartAt,
            PendingIntent pendingIntent) {
        // The caller uses this only before Android 12 or after
        // canScheduleExactAlarms() confirms that the exact call is allowed.
        alarmManager.setExact(
            AlarmManager.ELAPSED_REALTIME,
            restartAt,
            pendingIntent);
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        // Window focus can remain true after pause, and an obsolete Activity
        // can receive late input after a replacement registered. Neither may
        // enqueue keyboard edits in the current client's Qt UI.
        if (!resumed || INSTANCE.current() != this) {
            return true;
        }
        // Pico controller input is handled through OpenXR. Pico OS also sends
        // some controller buttons through Android, which can otherwise queue
        // indefinitely behind Qt's native event loop and trigger an input ANR.
        InputDevice device = event.getDevice();
        if (PicoKeyboardPolicy.forwardToQt(hasWindowFocus(),
                device != null && device.isExternal(),
                device != null && device.getKeyboardType() == InputDevice.KEYBOARD_TYPE_ALPHABETIC,
                event.isFromSource(InputDevice.SOURCE_KEYBOARD),
                event.isFromSource(InputDevice.SOURCE_GAMEPAD)
                    || event.isFromSource(InputDevice.SOURCE_JOYSTICK))) {
            return super.dispatchKeyEvent(event);
        }
        return true;
    }

    @Override
    public void onResume() {
        super.onResume();
        resumed = true;
        runShutdownStep("Web input", () -> OffscreenWebView.setInputForeground(this, hasWindowFocus()));
        if (INSTANCE.current() == this) PicoClientVisibility.foreground(this, true);
        if (INSTANCE.current() == this) AndroidAudioInput.setForeground(hasWindowFocus());
    }

    @Override
    public void onPause() {
        resumed = false;
        runShutdownStep("Web input", () -> OffscreenWebView.setInputForeground(this, false));
        if (INSTANCE.current() == this) PicoClientVisibility.foreground(this, false);
        if (INSTANCE.current() == this) AndroidAudioInput.setForeground(false);
        super.onPause();
    }

    @Override
    public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (INSTANCE.current() == this) {
            runShutdownStep("Web input", () -> OffscreenWebView.setInputForeground(this, resumed && focused));
            AndroidAudioInput.setForeground(resumed && focused);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        // Re-read the OS decision; do not trust a stale grantResults payload.
        if (INSTANCE.current() == this) AndroidAudioInput.permissionChanged();
    }
}
