// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

public final class PicoWebUrlPolicyTest {
    public static void main(String[] ignored) {
        int checks = 0;
        String[] forbidden = {"file:///private/file", "content://media/1", "intent://host/",
            "javascript:alert(1)", "hifi://example.test", "data:application/javascript,alert(1)",
            "data:text/html;unknown,value", "data:text/html;charset=ascii,body",
            "https://user:pass@example.test/", "https://example.test/%0a"};
        for (String value : forbidden) {
            if (PicoWebUrlPolicy.navigation(value) != null) throw new AssertionError("navigation allowed");
            checks++;
        }
        for (String value : new String[] {"https://example.test/", "http://example.test/",
                "data:text/html,%3Cb%3ELocal%3C%2Fb%3E", "data:text/html;charset=utf-8;base64,PGI+",
                "about:blank"}) {
            if (PicoWebUrlPolicy.navigation(value) == null) throw new AssertionError("navigation rejected");
            checks++;
        }
        for (String value : new String[] {"file:///android_asset/private", "content://other/data",
                "javascript:alert(1)", "intent://host/", "ftp://example.test/"}) {
            if (PicoWebUrlPolicy.resource(value)) throw new AssertionError("resource allowed");
            checks++;
        }
        if (!PicoWebUrlPolicy.resource("https://example.test/image.png")
                || !PicoWebUrlPolicy.resource("data:image/png;base64,AAAA")) {
            throw new AssertionError("supported resource rejected");
        }
        System.out.println("PASS native Pico WebView URL policy: " + (checks + 2) + " checks");
    }
}
