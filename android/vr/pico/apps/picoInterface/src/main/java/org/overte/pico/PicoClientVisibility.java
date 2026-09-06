package org.overte.pico;

import android.os.Handler;
import android.os.Looper;
import java.lang.ref.WeakReference;
import org.overte.security.SafeDiagnostics.Event;

/** Latest Activity foreground observation, separate from window focus/audio. */
final class PicoClientVisibility {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static WeakReference<Object> owner = new WeakReference<>(null);
    private static long generation;
    private static boolean foreground;
    private static boolean pending;
    private static boolean retryScheduled;
    private static boolean unavailableReported;
    private static long retryDelay = 50;
    private static final Runnable RETRY = PicoClientVisibility::retry;

    private PicoClientVisibility() {}

    // Implemented ONLY in the full-client target, never in early picoOpenXR.
    // True means queued/admitted, NOT applied or physically stopped.
    private static native boolean publish(long generation, boolean foreground);

    static synchronized void attach(Object instance) {
        if (instance == null) return;
        owner = new WeakReference<>(instance);
        update(false);
    }

    static synchronized void foreground(Object instance, boolean active) {
        if (instance == null || owner.get() != instance) return;
        if (foreground == active) {
            deliver();
        } else {
            update(active);
        }
    }

    static synchronized void detach(Object instance) {
        if (instance == null || owner.get() != instance) return;
        owner.clear();
        update(false);
    }

    private static void update(boolean active) {
        // Reserve the last signed generation for permanent denial, never wrap.
        if (generation >= Long.MAX_VALUE - 1) {
            generation = Long.MAX_VALUE;
            foreground = false;
        } else {
            ++generation;
            foreground = active;
        }
        pending = true;
        retryDelay = 50;
        deliver();
    }

    private static synchronized void retry() {
        retryScheduled = false;
        deliver();
    }

    private static void deliver() {
        if (retryScheduled) {
            MAIN.removeCallbacks(RETRY);
            retryScheduled = false;
        }
        if (!pending) return;
        boolean accepted = false;
        try {
            accepted = publish(generation, foreground);
        } catch (UnsatisfiedLinkError | RuntimeException failure) {
            // Qt may not have loaded the full client yet. Keep only the latest
            // observation; retries neither capture nor retain an Activity.
        }
        if (accepted) {
            pending = false;
            unavailableReported = false;
            return;
        }
        if (!unavailableReported) {
            RedactingDiagnostics.e(Event.CALLBACK_DISCARDED);
            unavailableReported = true;
        }
        // A destroyed owner cannot authorize future activity. Its final deny
        // is attempted immediately; if no full application exists, no future
        // owner is silently resumed. A replacement attach supplies a new deny.
        if (owner.get() != null) {
            retryScheduled = MAIN.postDelayed(RETRY, retryDelay);
            retryDelay = Math.min(1000, retryDelay * 2);
        }
    }
}
