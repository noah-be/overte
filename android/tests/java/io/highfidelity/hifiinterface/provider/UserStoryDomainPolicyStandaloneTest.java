package io.highfidelity.hifiinterface.provider;

public final class UserStoryDomainPolicyStandaloneTest {
    private static int assertions;

    public static void main(String[] arguments) {
        expect("hifi://welcome/1,2,3",
                UserStoryDomainPolicy.destinationUrl("welcome", "1,2,3"));
        expect("hifi://welcome/1,2,3",
                UserStoryDomainPolicy.destinationUrl("hifi://welcome", "/1,2,3"));
        expect("hifi://welcome",
                UserStoryDomainPolicy.destinationUrl("welcome", null));
        expect("hifi://welcome/1,2,3",
                UserStoryDomainPolicy.destinationUrl("hifi://welcome/", "/1,2,3"));
        expect("", UserStoryDomainPolicy.destinationUrl(null, "/1,2,3"));
        expect("", UserStoryDomainPolicy.destinationUrl("", "1,2,3"));
        expect("https://mv.overte.org/server/assets/place.jpg",
                UserStoryDomainPolicy.thumbnailUrl("/assets/place.jpg"));
        expect("https://cdn.example/place.jpg",
                UserStoryDomainPolicy.thumbnailUrl("https://cdn.example/place.jpg"));

        check(UserStoryDomainPolicy.shouldRequestNextPage(1, 2, 10));
        check(!UserStoryDomainPolicy.shouldRequestNextPage(2, 2, 10));
        check(!UserStoryDomainPolicy.shouldRequestNextPage(10, 11, 10));
        check(!UserStoryDomainPolicy.shouldRequestNextPage(11, 12, 10));
        check(!UserStoryDomainPolicy.shouldRequestNextPage(0, 2, 10));
        check(!UserStoryDomainPolicy.shouldRequestNextPage(1, 0, 10));
        check(!UserStoryDomainPolicy.shouldRequestNextPage(1, 2, 0));
        System.out.println("UserStoryDomainPolicyStandaloneTest: " + assertions
                + " assertions passed");
    }

    private static void expect(String expected, String actual) {
        assertions++;
        if (!expected.equals(actual)) {
            throw new AssertionError("expected " + expected + " but got " + actual);
        }
    }

    private static void check(boolean condition) {
        assertions++;
        if (!condition) {
            throw new AssertionError("condition was false");
        }
    }
}
