package io.highfidelity.hifiinterface;

public final class LegacyAdapterPositionPolicyStandaloneTest {
    private static int assertions;

    private static void check(boolean expected, int position, int itemCount) {
        assertions++;
        boolean actual = LegacyAdapterPositionPolicy.isValid(position, itemCount);
        if (actual != expected) {
            throw new AssertionError(
                    "position=" + position + " itemCount=" + itemCount + " expected=" + expected);
        }
    }

    public static void main(String[] args) {
        check(false, -1, 3);
        check(false, Integer.MIN_VALUE, 3);
        check(false, 0, 0);
        check(true, 0, 1);
        check(true, 2, 3);
        check(false, 3, 3);
        check(false, 4, 3);
        check(false, 0, -1);
        System.out.println("LegacyAdapterPositionPolicyStandaloneTest: " + assertions
                + " assertions passed");
    }
}
