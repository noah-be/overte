// Test-only controllable driver; never in the application source set.
package android.media;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
public final class AudioRecord {
    public static final int STATE_INITIALIZED = 1, READ_BLOCKING = 0;
    public static volatile int starts, stops, releases;
    public static volatile boolean blockStop;
    public static volatile CountDownLatch readEntered = new CountDownLatch(1);
    public static volatile AudioRecord latest;
    private boolean stopped, deliver;
    public AudioRecord(int source, int rate, int channels, int format, int buffer) { latest = this; }
    public static int getMinBufferSize(int rate, int channels, int format) { return 960; }
    public int getState() { return STATE_INITIALIZED; }
    public void startRecording() { ++starts; }
    public synchronized int read(byte[] bytes, int offset, int count, int mode) {
        readEntered.countDown();
        try { while (!stopped && !deliver) wait(); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); return -1; }
        if (stopped) return 0;
        deliver = false;
        java.util.Arrays.fill(bytes, offset, offset + count, (byte) 3);
        return count;
    }
    public synchronized void deliverOne() { deliver = true; notifyAll(); }
    public synchronized void stop() {
        ++stops;
        while (blockStop) {
            try { wait(5); } catch (InterruptedException error) { Thread.currentThread().interrupt(); break; }
        }
        stopped = true; notifyAll();
    }
    public synchronized void release() { ++releases; stopped = true; notifyAll(); }
    public static void nextRead() { readEntered = new CountDownLatch(1); }
    public static void awaitRead() throws Exception {
        if (!readEntered.await(2, TimeUnit.SECONDS)) throw new AssertionError("read did not start");
    }
}
