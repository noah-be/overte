package io.highfidelity.hifiinterface;

import java.io.IOException;
import java.net.URLDecoder;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public final class LegacyCrashAnnotationPolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static Map<String, String> decode(String query) throws Exception {
        Map<String, String> decoded = new LinkedHashMap<>();
        if (query.isEmpty()) {
            return decoded;
        }
        for (String pair : query.split("&")) {
            String[] parts = pair.split("=", 2);
            decoded.put(URLDecoder.decode(parts[0], "UTF-8"),
                    URLDecoder.decode(parts[1], "UTF-8"));
        }
        return decoded;
    }

    public static void main(String[] args) throws Exception {
        Map<String, String> input = new LinkedHashMap<>();
        input.put("Annotations/version", "a+b&c=d /ü%#");
        input.put("plain", "value");
        input.put("empty", "");
        input.put("null", null);
        input.put("Annotations/", "ignored");
        Map<String, String> decoded = decode(
                LegacyCrashAnnotationPolicy.encodeFailClosed(() -> input));
        check(decoded.size() == 2, "only non-empty keys and values must be encoded");
        check("a+b&c=d /ü%#".equals(decoded.get("version")),
                "reserved and Unicode values must round-trip");
        check("value".equals(decoded.get("plain")),
                "keys without a group prefix must remain intact");

        check("".equals(LegacyCrashAnnotationPolicy.encodeFailClosed(() -> null)),
                "null maps must fail closed");
        check("".equals(LegacyCrashAnnotationPolicy.encodeFailClosed(null)),
                "null sources must fail closed");
        check("".equals(LegacyCrashAnnotationPolicy.encodeFailClosed(() -> {
            throw new IOException("fixture");
        })), "read failures must not leak partial annotations");
        check("".equals(LegacyCrashAnnotationPolicy.encodeFailClosed(() -> {
            throw new IllegalStateException("fixture");
        })), "runtime parser failures must fail closed");

        AtomicInteger reads = new AtomicInteger();
        LegacyCrashAnnotationPolicy.encodeFailClosed(() -> {
            reads.incrementAndGet();
            return input;
        });
        check(reads.get() == 1, "the annotation source must be read exactly once");
        System.out.println("LegacyCrashAnnotationPolicyStandaloneTest: " + assertions
                + " assertions passed");
    }
}
