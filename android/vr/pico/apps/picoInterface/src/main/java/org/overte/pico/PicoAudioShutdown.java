// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

/** One bounded caller wait, even if an Android driver blocks inside stop/release.
 * A failed/pending cleanup prevents opening a second recorder. No retry loop.
 */
final class PicoAudioShutdown {
    private Thread worker;
    private volatile boolean succeeded = true;
    synchronized boolean ready() { return (worker == null || !worker.isAlive()) && succeeded; }
    synchronized boolean run(Runnable cleanup, long timeoutMillis) {
        if (!ready() || timeoutMillis <= 0) return false;
        succeeded = false;
        try {
            worker = new Thread(() -> {
                try { cleanup.run(); succeeded = true; }
                catch (RuntimeException | OutOfMemoryError error) { succeeded = false; }
            }, "Overte microphone cleanup");
            worker.setDaemon(true);
            worker.start();
            worker.join(timeoutMillis);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        } catch (RuntimeException | OutOfMemoryError error) {
            succeeded = false;
        }
        return ready();
    }
}
