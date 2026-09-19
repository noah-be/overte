// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Process;
import org.overte.security.SafeDiagnostics.Event;
import android.Manifest;
import android.content.pm.PackageManager;

/** Uses Android's public microphone API instead of Qt 5's deprecated OpenSL ES input. */
public final class AndroidAudioInput {
    private static final Object LOCK = new Object();
    private static final Object POLICY_LOCK = new Object();
    private static final PicoAudioShutdown SHUTDOWN = new PicoAudioShutdown();
    private static boolean foreground;
    private static boolean muted;
    private static volatile boolean nativeBridgeReady;
    private static volatile boolean captureAllowed;

    private static volatile boolean running;
    private static volatile AudioRecord recorder;
    private static Thread captureThread;

    private AndroidAudioInput() {
    }

    /** Gives native audio code a stable app-class-loader reference. */
    public static synchronized void initializeNativeBridge() {
        try {
            nativeInitialize();
            nativeBridgeReady = true;
        } catch (LinkageError | RuntimeException error) {
            // Reinitialization may fail while an earlier Activity still owns
            // a recorder. Revoke its Shared epoch before disabling this bridge
            // and retain the same bounded native cleanup path.
            publishPolicy(false);
            nativeBridgeReady = false;
            captureAllowed = false;
            stop();
            RedactingDiagnostics.e(Event.AUDIO_INTERRUPTED);
            return;
        }
        updateExternalPolicy();
        RedactingDiagnostics.i(Event.REDACTED);
    }

    /** Applies Android's public audio priority to the calling native audio thread. */
    public static int prioritizeCurrentThreadForAudio() {
        try {
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO);
            final int priority = Process.getThreadPriority(Process.myTid());
            RedactingDiagnostics.i(Event.REDACTED);
            return priority;
        } catch (IllegalArgumentException | SecurityException exception) {
            RedactingDiagnostics.e(Event.REDACTED);
            return Integer.MAX_VALUE;
        }
    }

    public static synchronized boolean start(
            String requestedSource, int sampleRate, int channelCount, int framesPerBuffer) {
        stop();
        if (!SHUTDOWN.ready()) { PicoAudioLifecycle.failed(); return false; }
        if (!nativeBridgeReady || !captureAllowed || !foreground || muted) return false;

        if (!microphonePermissionGranted()) {
            PicoAudioLifecycle.revoke();
            publishPolicy(false);
            RedactingDiagnostics.w(Event.PERMISSION_DENIED);
            return false;
        }
        if (!PicoAudioLifecycle.begin(true)) return false;

        final AndroidAudioInputPolicy.Source source =
            AndroidAudioInputPolicy.resolveSource(requestedSource);
        final AndroidAudioInputPolicy.Channel channel =
            AndroidAudioInputPolicy.resolveChannel(channelCount);
        final Integer requestedCallbackBytes = AndroidAudioInputPolicy.calculateCallbackBytes(
            sampleRate, channelCount, framesPerBuffer);
        if (source == null || channel == null || requestedCallbackBytes == null) {
            PicoAudioLifecycle.failed();
            RedactingDiagnostics.e(Event.REDACTED);
            return false;
        }

        final int audioSource = androidAudioSource(source);
        final int channelConfig = channel == AndroidAudioInputPolicy.Channel.STEREO
            ? AudioFormat.CHANNEL_IN_STEREO
            : AudioFormat.CHANNEL_IN_MONO;
        final int minimumBytes = AudioRecord.getMinBufferSize(
            sampleRate, channelConfig, AudioFormat.ENCODING_PCM_16BIT);
        if (minimumBytes <= 0) {
            PicoAudioLifecycle.failed();
            RedactingDiagnostics.e(Event.REDACTED);
            return false;
        }

        final AndroidAudioInputPolicy.BufferPlan bufferPlan =
            AndroidAudioInputPolicy.calculateBufferPlan(requestedCallbackBytes, minimumBytes);
        if (bufferPlan == null) {
            PicoAudioLifecycle.failed();
            RedactingDiagnostics.e(Event.REDACTED);
            return false;
        }
        final int callbackBytes = bufferPlan.callbackBytes;
        final int recorderBytes = bufferPlan.recorderBytes;
        final AudioRecord newRecorder;
        try {
            newRecorder = new AudioRecord(
                audioSource,
                sampleRate,
                channelConfig,
                AudioFormat.ENCODING_PCM_16BIT,
                recorderBytes);
        } catch (IllegalArgumentException | SecurityException exception) {
            PicoAudioLifecycle.failed();
            RedactingDiagnostics.e(Event.REDACTED);
            return false;
        }

        if (newRecorder.getState() != AudioRecord.STATE_INITIALIZED) {
            PicoAudioLifecycle.failed();
            RedactingDiagnostics.e(Event.REDACTED);
            SHUTDOWN.run(newRecorder::release, 1000);
            return false;
        }

        try {
            newRecorder.startRecording();
        } catch (IllegalStateException | SecurityException exception) {
            PicoAudioLifecycle.failed();
            RedactingDiagnostics.e(Event.REDACTED);
            SHUTDOWN.run(newRecorder::release, 1000);
            return false;
        }

        final Thread newCaptureThread;
        try {
            newCaptureThread = new Thread(
                () -> captureLoop(newRecorder, callbackBytes),
                "Overte Android microphone");
        } catch (RuntimeException | OutOfMemoryError exception) {
            PicoAudioLifecycle.failed();
            RedactingDiagnostics.e(Event.REDACTED);
            stopAndRelease(newRecorder);
            return false;
        }
        try {
            synchronized (LOCK) {
                recorder = newRecorder;
                running = true;
                captureThread = newCaptureThread;
                newCaptureThread.start();
            }
        } catch (RuntimeException | OutOfMemoryError exception) {
            PicoAudioLifecycle.failed();
            RedactingDiagnostics.e(Event.REDACTED);
            synchronized (LOCK) {
                if (recorder == newRecorder) {
                    running = false;
                    recorder = null;
                }
                if (captureThread == newCaptureThread) {
                    captureThread = null;
                }
            }
            stopAndRelease(newRecorder);
            return false;
        }
        RedactingDiagnostics.i(Event.REDACTED);
        return true;
    }

    public static synchronized void stop() {
        // This is a Shared device effect, not an external policy transition.
        // Publishing policy here would queue another refresh/start/stop loop.
        PicoAudioLifecycle.invalidate();
        final AudioRecord oldRecorder;
        final Thread oldThread;
        synchronized (LOCK) {
            running = false;
            oldRecorder = recorder;
            oldThread = captureThread;
            recorder = null;
            captureThread = null;
        }

        if (oldRecorder == null) {
            PicoAudioLifecycle.stopCompleted(SHUTDOWN.ready());
            return;
        }
        boolean stopped = SHUTDOWN.run(() -> {
            boolean clean = true;
            try { oldRecorder.stop(); }
            catch (RuntimeException error) { clean = false; }
            if (oldThread != null && oldThread != Thread.currentThread()) {
                try { oldThread.join(1000); }
                catch (InterruptedException error) { Thread.currentThread().interrupt(); clean = false; }
                if (oldThread.isAlive()) clean = false;
            }
            try { oldRecorder.release(); }
            catch (RuntimeException error) { clean = false; }
            if (!clean) throw new IllegalStateException("microphone cleanup incomplete");
        }, 1000);
        PicoAudioLifecycle.stopCompleted(stopped);
        if (stopped) RedactingDiagnostics.i(Event.AUDIO_STOPPED);
        else RedactingDiagnostics.w(Event.AUDIO_INTERRUPTED);
    }

    /** Only Shared refresh owns reopening; Java never replays an old request. */
    public static synchronized void setForeground(boolean active) {
        foreground = active;
        PicoAudioLifecycle.foreground(active);
        // Even duplicate visibility callbacks recheck a permission revoked in
        // Android settings. The Shared epoch gate itself coalesces duplicates.
        updateExternalPolicy();
    }

    public static synchronized void setMuted(boolean value) {
        muted = value;
        updateExternalPolicy();
    }

    public static synchronized void permissionChanged() {
        updateExternalPolicy();
    }

    private static void updateExternalPolicy() {
        boolean allowed = nativeBridgeReady && foreground && !muted
            && microphonePermissionGranted() && SHUTDOWN.ready();
        publishPolicy(allowed);
        // Invalidate native queued PCM BEFORE waiting for an Android driver.
        if (!captureAllowed) stop();
    }

    private static void publishPolicy(boolean allowed) {
        synchronized (POLICY_LOCK) {
            captureAllowed = allowed;
            if (!nativeBridgeReady) return;
            try {
                nativePolicyChanged(allowed);
            } catch (LinkageError | RuntimeException error) {
                nativeBridgeReady = false;
                captureAllowed = false;
                PicoAudioLifecycle.invalidate();
                RedactingDiagnostics.e(Event.AUDIO_INTERRUPTED);
            }
        }
    }

    private static int androidAudioSource(AndroidAudioInputPolicy.Source source) {
        switch (source) {
            case VOICE_COMMUNICATION: return MediaRecorder.AudioSource.VOICE_COMMUNICATION;
            case VOICE_RECOGNITION: return MediaRecorder.AudioSource.VOICE_RECOGNITION;
            case CAMCORDER: return MediaRecorder.AudioSource.CAMCORDER;
            default: return MediaRecorder.AudioSource.MIC;
        }
    }

    private static void stopAndRelease(AudioRecord activeRecorder) {
        boolean completed = SHUTDOWN.run(() -> {
            boolean clean = true;
            try { activeRecorder.stop(); }
            catch (RuntimeException exception) { clean = false; }
            try { activeRecorder.release(); }
            catch (RuntimeException exception) { clean = false; }
            if (!clean) throw new IllegalStateException("microphone cleanup incomplete");
        }, 1000);
        if (!completed) PicoAudioLifecycle.failed();
    }

    private static void captureLoop(AudioRecord activeRecorder, int callbackBytes) {
        prioritizeCurrentThreadForAudio();
        byte[] audio = null;
        try {
            audio = new byte[callbackBytes];
            while (running && recorder == activeRecorder) {
                if (!microphonePermissionGranted()) { PicoAudioLifecycle.revoke(); publishPolicy(false); break; }
                if (!captureAllowed || !PicoAudioLifecycle.mayCapture()) break;
                final int bytesRead = activeRecorder.read(
                    audio, 0, audio.length, AudioRecord.READ_BLOCKING);
                // stop() can unblock a pending read with a final positive buffer.
                // Re-check recorder identity after the blocking call so an old
                // source cannot enter a newly started source's native FIFO.
                final boolean ownsRecorder = recorder == activeRecorder;
                if (!microphonePermissionGranted()) { PicoAudioLifecycle.revoke(); publishPolicy(false); break; }
                if (!captureAllowed || !PicoAudioLifecycle.mayCapture()) break;
                if (AndroidAudioInputPolicy.shouldDeliverRead(bytesRead, running, ownsRecorder)
                        && PicoAudioCaptureState.shouldDeliver(
                            running, recorder, activeRecorder, bytesRead)) {
                    nativeOnAudioData(audio, bytesRead);
                } else if (!running || recorder != activeRecorder) {
                    break;
                } else {
                    RedactingDiagnostics.e(Event.REDACTED);
                    break;
                }
            }
        } catch (RuntimeException | OutOfMemoryError exception) {
            RedactingDiagnostics.e(Event.REDACTED);
        } finally {
            if (audio != null) java.util.Arrays.fill(audio, (byte) 0);
            boolean releasedRecorder = false;
            synchronized (LOCK) {
                // stop() may already own this recorder. Only an unexpected loop
                // exit while still current claims cleanup here. Complete release
                // before publishing an empty slot so start() cannot overlap it.
                if (recorder == activeRecorder) {
                    running = false;
                    // A driver/read failure denies capture until an external
                    // policy transition. It is never an automatic retry.
                    publishPolicy(false);
                    PicoAudioLifecycle.failed();
                    stopAndRelease(activeRecorder);
                    recorder = null;
                    if (captureThread == Thread.currentThread()) {
                        captureThread = null;
                    }
                    releasedRecorder = true;
                }
            }
            if (releasedRecorder) {
                RedactingDiagnostics.w(Event.REDACTED);
            }
        }
    }

    private static boolean microphonePermissionGranted() {
        try {
            PicoInterfaceActivity activity = PicoInterfaceActivity.getInstance();
            return activity != null && activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED;
        } catch (RuntimeException error) {
            RedactingDiagnostics.w(Event.PERMISSION_DENIED);
            return false;
        }
    }

    private static native void nativeInitialize();
    private static native void nativePolicyChanged(boolean captureAllowed);
    private static native void nativeOnAudioData(byte[] audio, int bytesRead);
}
