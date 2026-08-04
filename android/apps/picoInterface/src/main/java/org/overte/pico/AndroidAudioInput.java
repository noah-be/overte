// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Process;
import android.util.Log;

/** Uses Android's public microphone API instead of Qt 5's deprecated OpenSL ES input. */
public final class AndroidAudioInput {
    private static final String TAG = "OverteAudioInput";
    private static final Object LOCK = new Object();

    private static volatile boolean running;
    private static AudioRecord recorder;
    private static Thread captureThread;

    private AndroidAudioInput() {
    }

    /** Gives native audio code a stable app-class-loader reference. */
    public static void initializeNativeBridge() {
        nativeInitialize();
        Log.i(TAG, "Initialized native microphone bridge");
    }

    /** Applies Android's public audio priority to the calling native audio thread. */
    public static int prioritizeCurrentThreadForAudio() {
        try {
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO);
            final int priority = Process.getThreadPriority(Process.myTid());
            Log.i(TAG, "Prioritized native audio thread tid=" + Process.myTid()
                + ", priority=" + priority);
            return priority;
        } catch (IllegalArgumentException | SecurityException exception) {
            Log.e(TAG, "Could not prioritize native audio thread", exception);
            return Integer.MAX_VALUE;
        }
    }

    public static boolean start(int sampleRate, int channelCount, int framesPerBuffer) {
        stop();

        final int channelConfig = channelCount == 2
            ? AudioFormat.CHANNEL_IN_STEREO
            : AudioFormat.CHANNEL_IN_MONO;
        final int minimumBytes = AudioRecord.getMinBufferSize(
            sampleRate, channelConfig, AudioFormat.ENCODING_PCM_16BIT);
        if (minimumBytes <= 0) {
            Log.e(TAG, "Unsupported capture format; getMinBufferSize=" + minimumBytes);
            return false;
        }

        final int callbackBytes = Math.max(
            framesPerBuffer * channelCount * Short.BYTES,
            sampleRate * channelCount * Short.BYTES / 50);
        final int recorderBytes = Math.max(minimumBytes, callbackBytes * 2);
        final AudioRecord newRecorder;
        try {
            newRecorder = new AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                channelConfig,
                AudioFormat.ENCODING_PCM_16BIT,
                recorderBytes);
        } catch (IllegalArgumentException | SecurityException exception) {
            Log.e(TAG, "Could not create AudioRecord", exception);
            return false;
        }

        if (newRecorder.getState() != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord was not initialized");
            newRecorder.release();
            return false;
        }

        try {
            newRecorder.startRecording();
        } catch (IllegalStateException | SecurityException exception) {
            Log.e(TAG, "Could not start AudioRecord", exception);
            newRecorder.release();
            return false;
        }

        synchronized (LOCK) {
            recorder = newRecorder;
            running = true;
            captureThread = new Thread(
                () -> captureLoop(newRecorder, callbackBytes),
                "Overte Android microphone");
            captureThread.start();
        }
        Log.i(TAG, "Started AudioRecord MIC at " + sampleRate + " Hz, channels="
            + channelCount + ", callbackBytes=" + callbackBytes);
        return true;
    }

    public static void stop() {
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
            return;
        }
        try {
            oldRecorder.stop();
        } catch (IllegalStateException exception) {
            Log.w(TAG, "AudioRecord was already stopped", exception);
        }
        if (oldThread != null && oldThread != Thread.currentThread()) {
            try {
                oldThread.join(1000);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
        }
        oldRecorder.release();
        Log.i(TAG, "Stopped AudioRecord MIC");
    }

    private static void captureLoop(AudioRecord activeRecorder, int callbackBytes) {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO);
        final byte[] audio = new byte[callbackBytes];
        while (running && recorder == activeRecorder) {
            final int bytesRead = activeRecorder.read(
                audio, 0, audio.length, AudioRecord.READ_BLOCKING);
            if (bytesRead > 0) {
                nativeOnAudioData(audio, bytesRead);
            } else if (!running || recorder != activeRecorder) {
                break;
            } else {
                Log.e(TAG, "AudioRecord read failed: " + bytesRead);
                break;
            }
        }
    }

    private static native void nativeInitialize();
    private static native void nativeOnAudioData(byte[] audio, int bytesRead);
}
