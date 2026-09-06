// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

public final class PicoRestartUrlPolicyTest {
    private static int checks;
    static void check(boolean result) {
        if (!result) throw new AssertionError("native URL contract failed at check " + checks);
        checks++;
    }
    public static void main(String[] ignored) {
        String[] rejected = {
            "javascript:alert(1)", "data:text/html,unsafe", "content://other.app/private",
            "intent://example/#Intent;scheme=https;end", "ftp://example.test/world",
            "hifiapp:/inventory", "example.test/world", "hifi:///1,2,3", "https:///world",
            "https://user:secret@example.test/world", "file://example.test/private",
            "file://localhost:80/private", "file:///safe/../private", "file:///safe/%2e%2e/private",
            "file:///safe/%5cprivate", "hifi://example.test/world\n--url hifi://other",
            "hifi://example.test/%0a", "hifi://example.test/%GG", "hifi://example.test/\ud800",
            "hifi://example.test/abc\u202elmth", "https://example.test:99999/",
            "https://example.test%2f.other/", "https://evil host/", "https://example.test:-2/",
            "hifi://example.test/ --test malicious.js", " hifi://example.test",
        };
        for (String input : rejected) check(PicoRestartUrlPolicy.worldUrl(input) == null);
        String[] allowed = {"hifi://example.test/1,2,3", "http://example.test/world.json",
            "https://example.test/world.json", "file:///~/serverless/world.json",
            "https://[::1]:443/world", "file://localhost/world.json"};
        for (String input : allowed) check(input.equals(PicoRestartUrlPolicy.worldUrl(input)));
        check("hifi://xn--mnchen-3ya.example/Caf%C3%A9/%F0%9F%99%82".equals(
            PicoRestartUrlPolicy.worldUrl("hifi://münchen.example/Cafe\u0301/🙂")));
        check(PicoRestartUrlPolicy.worldUrl("hifi://example.test/" + repeat("界", 4096)) == null);
        String prefix = "hifi://example.test/";
        check(PicoRestartUrlPolicy.worldUrl(prefix + repeat("a", 4096 - prefix.length())) != null);
        check(PicoRestartUrlPolicy.worldUrl(prefix + repeat("a", 4097 - prefix.length())) == null);
        check(PicoRestartUrlPolicy.BASE.equals(PicoRestartUrlPolicy.arguments(PicoRestartUrlPolicy.BASE)));
        check(PicoRestartUrlPolicy.arguments("--display=OpenXR --url hifi://example.test") != null);
        check(PicoRestartUrlPolicy.arguments("--display=OpenXR --test private.js") == null);
        check(PicoRestartUrlPolicy.arguments(null) == null);
        check(PicoRestartUrlPolicy.arguments("") == null);
        System.out.println("PASS native Pico restart URL policy: " + checks + " checks");
    }
    static String repeat(String text, int count) {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < count; index++) result.append(text);
        return result.toString();
    }
}
