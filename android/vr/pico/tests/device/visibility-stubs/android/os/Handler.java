package android.os;
import java.util.ArrayList;
import java.util.List;
/** Test-only deterministic main-loop scheduling; no thread or Android runtime. */
public final class Handler {
    private static final List<Runnable> pending = new ArrayList<>();
    public Handler(Looper ignored) {}
    public boolean postDelayed(Runnable action, long delay) {
        if (delay < 50 || delay > 1000) throw new AssertionError("retry delay");
        pending.add(action);
        return true;
    }
    public void removeCallbacks(Runnable action) { pending.removeIf(item -> item == action); }
    public static int pendingCount() { return pending.size(); }
    public static void runNext() {
        if (pending.size() != 1) throw new AssertionError("one pending retry required");
        pending.remove(0).run();
    }
}
