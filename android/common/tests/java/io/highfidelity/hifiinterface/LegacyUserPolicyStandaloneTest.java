package io.highfidelity.hifiinterface;

public final class LegacyUserPolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check(LegacyUserPolicy.isUsablePage(true, true, true, true, 0),
                "empty valid pages must pass");
        check(!LegacyUserPolicy.isUsablePage(false, true, true, true, 1), "HTTP errors must fail");
        check(!LegacyUserPolicy.isUsablePage(true, false, false, false, 1), "null body must fail");
        check(!LegacyUserPolicy.isUsablePage(true, true, false, false, 1), "null data must fail");
        check(!LegacyUserPolicy.isUsablePage(true, true, true, false, 1), "null users must fail");
        check(!LegacyUserPolicy.isUsablePage(true, true, true, true, -1), "negative totals must fail");
        check("".equals(LegacyUserPolicy.safeText(null)), "null text must be empty");
        check("name".equals(LegacyUserPolicy.safeText("name")), "text must be preserved");
        check(!LegacyUserPolicy.hasText(null), "null is not text");
        check(!LegacyUserPolicy.hasText("  "), "whitespace is not text");
        check(LegacyUserPolicy.hasText(" value "), "non-whitespace is text");
        check(LegacyUserPolicy.isFriend("friend"), "friend connection must match");
        check(!LegacyUserPolicy.isFriend(null), "null connection must not match");
        check(!LegacyUserPolicy.isFriend("Friend"), "connection matching remains exact");
        check("root".equals(LegacyUserPolicy.locationName("root", "domain")),
                "root must take precedence");
        check("domain".equals(LegacyUserPolicy.locationName("", "domain")),
                "empty root must fall back to domain");
        check("".equals(LegacyUserPolicy.locationName(null, null)),
                "missing location must be empty");
        System.out.println("LegacyUserPolicyStandaloneTest: " + assertions + " assertions passed");
    }
}
