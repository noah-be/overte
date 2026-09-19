// Actual Java capture class + original native policy callback; driver/Qt are test-only.
package org.overte.pico;
import android.media.AudioRecord;
public final class PicoAudioPolicyBindingTest {
    private static native boolean allowed();
    private static native long epoch();
    private static native int clears();
    private static native int queued();
    private static native int delivered();
    private static native void acknowledgeRefresh();
    private static native void failInitialization(boolean fail);
    private static void check(boolean condition) { if (!condition) throw new AssertionError(); }
    private static boolean start() { return AndroidAudioInput.start("mic", 24000, 1, 480); }
    private static void waitReleased(int previous) throws Exception {
        long until = System.nanoTime() + 2_000_000_000L;
        while (AudioRecord.releases <= previous && System.nanoTime() < until) Thread.sleep(2);
        check(AudioRecord.releases > previous);
    }
    public static void main(String[] args) throws Exception {
        System.load(args[0]);
        if (args.length > 1) {
            AndroidAudioInput.setForeground(true);
            AndroidAudioInput.initializeNativeBridge();
            check(!allowed() && !start() && AudioRecord.starts == 0);
            System.out.println("Missing native policy binding fails closed PASS");
            return;
        }
        // Policy before bridge initialization is remembered but cannot capture.
        AndroidAudioInput.setForeground(true);
        check(!allowed() && !start() && AudioRecord.starts == 0);
        AndroidAudioInput.initializeNativeBridge();
        check(allowed() && queued() == 1 && AudioRecord.starts == 0);
        long first = epoch(); int changes = clears();
        AndroidAudioInput.setForeground(true);
        check(epoch() == first && clears() == changes); // duplicate is idempotent
        acknowledgeRefresh();

        AudioRecord.nextRead(); check(start()); AudioRecord.awaitRead();
        check(clears() == changes && queued() == 1); // internal start does not publish
        int opened = AudioRecord.starts;
        AndroidAudioInput.stop();
        check(allowed() && clears() == changes && queued() == 1);
        check(AudioRecord.releases == 1);

        // Mute closes the OS input and cannot resume on subsequent focus.
        AudioRecord.nextRead(); check(start()); AudioRecord.awaitRead();
        AndroidAudioInput.setMuted(true);
        check(!allowed() && AudioRecord.releases == 2 && !start());
        AndroidAudioInput.setForeground(false);
        AndroidAudioInput.setForeground(true);
        check(!allowed() && AudioRecord.starts == opened + 1);
        AndroidAudioInput.setMuted(false);
        check(allowed() && epoch() != first && AudioRecord.starts == opened + 1);
        acknowledgeRefresh();

        // Revocation DURING the blocking read must reject that returned buffer.
        AudioRecord.nextRead(); check(start()); AudioRecord.awaitRead();
        int oldReleased = AudioRecord.releases, oldDelivered = delivered();
        PicoInterfaceActivity.granted = false;
        AudioRecord.latest.deliverOne();
        waitReleased(oldReleased);
        check(!allowed() && delivered() == oldDelivered);
        AndroidAudioInput.stop();
        AndroidAudioInput.setForeground(true); // duplicate observation rereads permission
        check(!allowed() && !start());
        PicoInterfaceActivity.granted = true;
        AndroidAudioInput.permissionChanged();
        check(allowed());

        // No owner/hidden/unmute cannot grant; only fresh eligible policy can.
        PicoInterfaceActivity.present = false;
        AndroidAudioInput.permissionChanged(); check(!allowed());
        PicoInterfaceActivity.present = true;
        AndroidAudioInput.setForeground(false);
        AndroidAudioInput.setMuted(false); check(!allowed());
        AndroidAudioInput.setForeground(true); check(allowed());

        PicoInterfaceActivity.permissionFailure = true;
        AndroidAudioInput.permissionChanged(); check(!allowed() && !start());
        PicoInterfaceActivity.permissionFailure = false;
        AndroidAudioInput.permissionChanged(); check(allowed());

        // A failed Activity/bridge reinitialization must close existing capture.
        AudioRecord.nextRead(); check(start()); AudioRecord.awaitRead();
        oldReleased = AudioRecord.releases;
        failInitialization(true);
        AndroidAudioInput.initializeNativeBridge();
        check(!allowed() && AudioRecord.releases == oldReleased + 1 && !start());
        failInitialization(false);
        AndroidAudioInput.initializeNativeBridge();
        check(allowed());

        // Blocked cleanup denies Shared synchronously and prevents another driver.
        AudioRecord.nextRead(); check(start()); AudioRecord.awaitRead();
        opened = AudioRecord.starts;
        AudioRecord.blockStop = true;
        long before = System.nanoTime();
        AndroidAudioInput.setMuted(true);
        long elapsed = System.nanoTime() - before;
        check(!allowed() && elapsed < 2_500_000_000L);
        AndroidAudioInput.setMuted(false);
        check(!allowed() && !start() && AudioRecord.starts == opened);
        AudioRecord.blockStop = false;
        Thread.sleep(30);
        AndroidAudioInput.setForeground(false);
        check(!allowed());
        System.out.println("Pico live Java/JNI policy, mute, late focus, revoke and bounded cleanup PASS (test driver only)");
    }
}
