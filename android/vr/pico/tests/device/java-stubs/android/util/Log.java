// Test-only capture sink. This file is not in the application source set.
package android.util;
public final class Log {
    public static String tag, text, level;
    public static int e(String t, String value) { tag=t; text=value; level="E"; return 0; }
    public static int w(String t, String value) { tag=t; text=value; level="W"; return 0; }
    public static int i(String t, String value) { tag=t; text=value; level="I"; return 0; }
}
