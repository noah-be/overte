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
import android.util.Log;
import android.view.KeyEvent;

import org.qtproject.qt5.android.bindings.QtActivity;

import io.highfidelity.utils.HifiUtils;

public final class PicoInterfaceActivity extends QtActivity {
    private static final String TAG = "OvertePico";
    private static final PicoActivityInstancePolicy<PicoInterfaceActivity> INSTANCE =
        new PicoActivityInstancePolicy<>();

    static {
        // Qt 5 resolves OpenSSL dynamically.  Android packages the libraries
        // without their 1.1 suffix, so preload them to make their SONAMEs
        // available before QtNetwork initializes TLS.
        System.loadLibrary("crypto");
        System.loadLibrary("ssl");
        System.loadLibrary("picoOpenXR");
    }

    private native boolean initializeOpenXRLoader();
    private native void releaseOpenXRActivity();

    public static PicoInterfaceActivity getInstance() {
        return INSTANCE.current();
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        INSTANCE.register(this);
        APPLICATION_PARAMETERS = PicoInterfaceActivityPolicy.applicationParameters(
            getIntent().hasExtra("applicationArguments"),
            getIntent().getStringExtra("applicationArguments"),
            getCacheDir().getAbsolutePath());

        HifiUtils.upackAssets(getAssets(), getCacheDir().getAbsolutePath());

        if (!initializeOpenXRLoader()) {
            Log.e(TAG, "The Android OpenXR loader could not be initialized");
        }

        super.onCreate(savedInstanceState);
        OffscreenWebView.initializeNativeBridge();
        AndroidAudioInput.initializeNativeBridge();
    }

    public static void scheduleRestart(String applicationArguments) {
        final PicoInterfaceActivity activity = INSTANCE.current();
        if (activity == null) {
            Log.e(TAG, "Cannot restart: activity is unavailable");
            return;
        }
        if (!RestartArguments.store(activity, applicationArguments)) {
            Log.e(TAG, "Cannot restart: arguments could not be stored privately");
            return;
        }
        Log.i(TAG, "Scheduling application restart");

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
                Log.e(TAG, "Cannot restart: AlarmManager is unavailable");
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
            Log.e(TAG, "Cannot restart: scheduling failed", exception);
            RestartArguments.clear(activity);
            return;
        }

        activity.finishAffinity();
        new android.os.Handler(activity.getMainLooper()).postDelayed(() -> {
            Log.i(TAG, "Terminating old application process for restart");
            Process.killProcess(Process.myPid());
        }, 750);
    }

    @Override
    protected void onDestroy() {
        INSTANCE.clear(this);
        try {
            runShutdownStep("WebViews", OffscreenWebView::destroyAll);
            runShutdownStep("microphone", AndroidAudioInput::stop);
            runShutdownStep("OpenXR Activity", this::releaseOpenXRActivity);
        } finally {
            super.onDestroy();
        }
    }

    private static void runShutdownStep(String name, Runnable cleanup) {
        try {
            cleanup.run();
        } catch (RuntimeException | OutOfMemoryError exception) {
            Log.e(TAG, "Failed to clean up " + name, exception);
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
        // Pico controller input is handled through OpenXR. Pico OS also sends
        // some controller buttons through Android, which can otherwise queue
        // indefinitely behind Qt's native event loop and trigger an input ANR.
        return true;
    }
}
