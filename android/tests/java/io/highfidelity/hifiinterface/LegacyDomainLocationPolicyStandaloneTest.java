package io.highfidelity.hifiinterface;

import java.util.Locale;

public final class LegacyDomainLocationPolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean expected, String location, String candidate) {
        assertions++;
        boolean actual = LegacyDomainLocationPolicy.matchesRoot(location, candidate);
        if (actual != expected) {
            throw new AssertionError(location + " versus " + candidate + " expected=" + expected);
        }
    }

    public static void main(String[] args) {
        check(true, "hifi://place", "hifi://place/1,2,3");
        check(true, "HIFI://PLACE/path", "hifi://place");
        check(false, "hifi://place", "hifi://another/path");
        check(false, null, "hifi://place");
        check(false, "hifi://place", null);
        check(false, "place", "hifi://place");
        check(false, "hifi:///path", "hifi://place");
        check(true, " hifi://place/path ", "hifi://place/other");
        check(true, "hifi://place?x=1", "hifi://place#fragment");

        Locale previous = Locale.getDefault();
        try {
            Locale.setDefault(new Locale("tr", "TR"));
            check(true, "HIFI://ISLAND", "hifi://island/path");
        } finally {
            Locale.setDefault(previous);
        }
        System.out.println("LegacyDomainLocationPolicyStandaloneTest: " + assertions
                + " assertions passed");
    }
}
