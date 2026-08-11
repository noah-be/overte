package io.highfidelity.hifiinterface;

public final class LegacyAdapterPositionPolicy {
    private LegacyAdapterPositionPolicy() {
    }

    public static boolean isValid(int position, int itemCount) {
        return position >= 0 && position < itemCount;
    }
}
