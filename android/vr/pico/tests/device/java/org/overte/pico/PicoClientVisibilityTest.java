package org.overte.pico;

import android.os.Handler;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class PicoClientVisibilityTest {
    private static native void initialize();
    private static native void shutdown();
    private static native void qt(boolean active);
    private static native void events();
    private static native boolean allowed();
    private static native void takeTicket();
    private static native boolean ticketCurrent();
    private static native void stop();
    private static void need(boolean value) { if (!value) throw new AssertionError(); }

    public static void main(String[] args) throws Exception {
        Object first = new Object();
        PicoClientVisibility.attach(first);
        PicoClientVisibility.foreground(first, true);
        PicoClientVisibility.foreground(first, false);
        need(Handler.pendingCount() == 1); // Missing full DSO: latest state retained.
        System.load(args[0]);
        Handler.runNext(); // Library exists but QCoreApplication does not.
        need(Handler.pendingCount() == 1);
        initialize();
        try {
        if (args.length > 1) {
            for (int i = 0; i < 8; ++i) Handler.runNext();
            need(Handler.pendingCount() == 1);
            // Old/mismatched library never acknowledges a native observation.
            Field pending = PicoClientVisibility.class.getDeclaredField("pending");
            pending.setAccessible(true);
            need(pending.getBoolean(null));
            PicoClientVisibility.detach(first);
            need(Handler.pendingCount() == 0);
            return;
        }
        Handler.runNext();
        need(Handler.pendingCount() == 0);
        events();
        qt(true);
        need(!allowed()); // Early pending native pause vetoes later Qt active.
        PicoClientVisibility.foreground(first, true);
        need(!allowed()); // Admitted queue is not an applied receipt.
        events(); need(allowed());
        takeTicket();
        PicoClientVisibility.foreground(first, true);
        events(); need(ticketCurrent()); // Duplicate does not cancel HTTP.

        PicoClientVisibility.foreground(first, false);
        PicoClientVisibility.foreground(first, true);
        events();
        need(allowed() && !ticketCurrent()); // Accepted pause barrier survives quick resume.
        takeTicket();
        PicoClientVisibility.foreground(first, false);
        events(); need(!allowed() && !ticketCurrent());
        qt(false);
        PicoClientVisibility.foreground(first, true);
        events(); need(!allowed()); // Native allow cannot override Qt denial.
        qt(true); need(allowed());

        Object replacement = new Object();
        PicoClientVisibility.attach(replacement);
        PicoClientVisibility.foreground(first, true);
        PicoClientVisibility.detach(first);
        events(); need(!allowed()); // Old Activity cannot revoke/activate replacement.
        PicoClientVisibility.foreground(replacement, true);
        events(); need(allowed());
        PicoClientVisibility.foreground(first, false);
        PicoClientVisibility.detach(first);
        events(); need(allowed()); // Stale owner cannot veto an active replacement.
        Thread nativePause = new Thread(() -> PicoClientVisibility.foreground(replacement, false));
        nativePause.start(); nativePause.join();
        need(allowed()); // JNI from a foreign thread still queues, not a stop receipt.
        events(); need(!allowed());
        PicoClientVisibility.foreground(replacement, true);
        events(); need(allowed());
        takeTicket();
        PicoClientVisibility.foreground(replacement, false);
        PicoClientVisibility.foreground(replacement, true);
        PicoClientVisibility.foreground(replacement, false);
        events(); need(!allowed() && !ticketCurrent());

        Method publish = PicoClientVisibility.class.getDeclaredMethod("publish", long.class, boolean.class);
        publish.setAccessible(true);
        need((Boolean) publish.invoke(null, 1L, true));
        events(); need(!allowed()); // Delayed stale native generation is discarded.
        need(!(Boolean) publish.invoke(null, 0L, true));

        Field generation = PicoClientVisibility.class.getDeclaredField("generation");
        generation.setAccessible(true);
        generation.setLong(null, Long.MAX_VALUE - 1);
        PicoClientVisibility.foreground(replacement, true);
        events(); need(!allowed()); // Exhaustion is permanent denial, never wrap.
        PicoClientVisibility.foreground(replacement, true);
        events(); need(!allowed());
        PicoClientVisibility.detach(replacement);
        need(Handler.pendingCount() == 0);
        stop(); qt(true); events(); need(!allowed());
        } finally {
            shutdown();
        }
    }
}
