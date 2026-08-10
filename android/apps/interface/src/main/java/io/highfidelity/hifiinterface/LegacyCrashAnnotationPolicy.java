package io.highfidelity.hifiinterface;

import java.net.URLEncoder;
import java.util.Map;

/** Fail-closed encoding boundary for concurrently written crash annotations. */
public final class LegacyCrashAnnotationPolicy {
    public interface AnnotationSource {
        Map<String, String> read() throws Exception;
    }

    private LegacyCrashAnnotationPolicy() {
    }

    public static String encodeFailClosed(AnnotationSource source) {
        if (source == null) {
            return "";
        }
        try {
            Map<String, String> annotations = source.read();
            if (annotations == null) {
                return "";
            }
            StringBuilder encoded = new StringBuilder();
            for (Map.Entry<String, String> annotation : annotations.entrySet()) {
                String key = annotation.getKey();
                String value = annotation.getValue();
                if (key == null || value == null || value.isEmpty()) {
                    continue;
                }
                int separator = key.indexOf('/');
                if (separator >= 0) {
                    key = key.substring(separator + 1);
                }
                if (key.isEmpty()) {
                    continue;
                }
                if (encoded.length() > 0) {
                    encoded.append('&');
                }
                encoded.append(URLEncoder.encode(key, "UTF-8"));
                encoded.append('=');
                encoded.append(URLEncoder.encode(value, "UTF-8"));
            }
            return encoded.toString();
        } catch (Exception error) {
            return "";
        }
    }
}
