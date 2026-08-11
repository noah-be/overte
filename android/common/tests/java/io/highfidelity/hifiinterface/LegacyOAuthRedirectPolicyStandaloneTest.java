package io.highfidelity.hifiinterface;

public final class LegacyOAuthRedirectPolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        String configured = "https://trusted.example/callback";
        check(LegacyOAuthRedirectPolicy.matches(
                        configured, "https://trusted.example/callback?code=a&state=b"),
                "OAuth response query parameters must be accepted");
        check(LegacyOAuthRedirectPolicy.matches(
                        "HTTPS://TRUSTED.EXAMPLE/callback", "https://trusted.example/callback"),
                "scheme and host matching must be case-insensitive");

        String[] rejected = {
                null, "", " ", "relative/callback", "bad uri [",
                "https://trusted.example/callback.evil/path",
                "https://trusted.example/callback-attacker",
                "https://trusted.example/callback/",
                "https://trusted.example/other",
                "https://attacker.trusted.example/callback",
                "https://trusted.example@attacker.example/callback",
                "http://trusted.example/callback",
                "https://trusted.example:443/callback",
                "https://trusted.example/callback#fragment",
                "https://trusted.example/%63allback",
                "https://trusted.example/callback%2F"
        };
        for (String candidate : rejected) {
            check(!LegacyOAuthRedirectPolicy.matches(configured, candidate),
                    "OAuth redirect components must match exactly");
        }
        String[] unsafeConfigured = {
                null, "", "relative", "custom:callback",
                "https://user@trusted.example/callback",
                "https://trusted.example/callback?fixed=1",
                "https://trusted.example/callback#fragment"
        };
        for (String unsafe : unsafeConfigured) {
            check(!LegacyOAuthRedirectPolicy.matches(
                            unsafe, "https://trusted.example/callback?code=a"),
                    "unsafe configured redirects must fail closed");
        }
        System.out.println("LegacyOAuthRedirectPolicyStandaloneTest: " + assertions
                + " assertions passed");
    }
}
