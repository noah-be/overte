// Test-only Android provider boundary; actual module API is compiled separately.
package org.overte.documents;
import android.content.Intent;
public final class DocumentAdapter {
    public static void initialize(DocumentHost owner) {}
    public static void foreground(DocumentHost owner) {}
    public static void detach(DocumentHost owner) {}
    public static boolean activityResult(DocumentHost owner,int code,int result,Intent data) {return false;}
}
