// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
public final class PicoAudioLifecycleTest {
    static void check(boolean value) { if (!value) throw new AssertionError("Pico audio lifecycle"); }
    public static void main(String[] args) throws Exception {
        System.load(args[0]);
        check(!PicoAudioLifecycle.mayCapture());
        check(!PicoAudioLifecycle.begin(true)); // background cannot capture
        PicoAudioLifecycle.foreground(true);
        check(!PicoAudioLifecycle.begin(false));
        check(PicoAudioLifecycle.begin(true));
        PicoAudioLifecycle.revoke(); check(!PicoAudioLifecycle.mayCapture());
        check(PicoAudioLifecycle.begin(true));
        PicoAudioLifecycle.foreground(false); check(!PicoAudioLifecycle.mayCapture());
        PicoAudioLifecycle.foreground(true); check(PicoAudioLifecycle.mayCapture());
        PicoAudioLifecycle.invalidate(); check(!PicoAudioLifecycle.mayCapture());
        PicoAudioLifecycle.stopCompleted(false); check(!PicoAudioLifecycle.mayCapture());
        PicoAudioLifecycle.foreground(false); PicoAudioLifecycle.foreground(true);
        check(!PicoAudioLifecycle.mayCapture()); // no automatic recovery after failure
        check(PicoAudioLifecycle.begin(true));
        PicoAudioLifecycle.stopCompleted(true); check(!PicoAudioLifecycle.mayCapture());

        PicoAudioShutdown shutdown = new PicoAudioShutdown();
        CountDownLatch release = new CountDownLatch(1), done = new CountDownLatch(1);
        long begin = System.nanoTime();
        check(!shutdown.run(() -> {
            try { release.await(); }
            catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new IllegalStateException(); }
            finally { done.countDown(); }
        }, 30));
        check(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - begin) < 500);
        check(!shutdown.ready());
        check(!shutdown.run(() -> { throw new AssertionError("second cleanup forbidden"); }, 30));
        release.countDown(); check(done.await(1, TimeUnit.SECONDS));
        // Worker terminates just after the final callback; bounded explicit await.
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(1);
        while (!shutdown.ready() && System.nanoTime() < deadline) Thread.yield();
        check(shutdown.ready());
        check(shutdown.run(() -> {}, 1000));
        check(!shutdown.run(() -> { throw new IllegalStateException("private fixture"); }, 1000));
        check(!shutdown.ready());
        System.out.println("Actual SH-006 JNI gate and bounded shutdown PASS (no AudioRecord device)");
    }
}
