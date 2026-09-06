// Test-only host thread-priority boundary.
package android.os;
public final class Process {
    public static final int THREAD_PRIORITY_URGENT_AUDIO = -19;
    public static void setThreadPriority(int priority) { }
    public static int getThreadPriority(int tid) { return THREAD_PRIORITY_URGENT_AUDIO; }
    public static int myTid() { return 1; }
}
