package org.overte.phone;

/** Host-side device matrix and adversarial checks for touch UI measurements. */
public final class PhoneTouchUiMetricsPolicyStandaloneTest {
    private static int assertions;

    private PhoneTouchUiMetricsPolicyStandaloneTest() {
    }

    public static void main(String[] args) {
        rejectsInvalidSurfaces();
        preservesAsymmetricInsetsAndCapabilities();
        derivesStableDensityScaleWithoutImeZooming();
        separatesLegacyImeFromPersistentProtection();
        clampsHostileMeasurements();
        snapshotsHaveStableValueSemantics();
        coversRepresentativeDeviceMatrix();
        runsBoundedDeterministicPerformanceMatrix();
        System.out.println("Phone touch UI metrics assertions passed: " + assertions);
    }

    private static void separatesLegacyImeFromPersistentProtection() {
        PhoneTouchUiMetricsPolicy.LegacyInsets keyboard =
                PhoneTouchUiMetricsPolicy.normalizeLegacyInsets(
                        1, 2, 3, 420, 24,
                        4, 5, 6, 18,
                        92, 7, 31, 40);
        check(keyboard.left == 92 && keyboard.top == 7 && keyboard.right == 31);
        check(keyboard.bottom == 40);
        check(keyboard.imeBottom == 420);

        PhoneTouchUiMetricsPolicy.LegacyInsets navigationOnly =
                PhoneTouchUiMetricsPolicy.normalizeLegacyInsets(
                        0, 0, 0, 24, 24,
                        0, 0, 0, 32,
                        0, 0, 0, 0);
        check(navigationOnly.bottom == 32);
        check(navigationOnly.imeBottom == 0);

        PhoneTouchUiMetricsPolicy.LegacyInsets hostile =
                PhoneTouchUiMetricsPolicy.normalizeLegacyInsets(
                        -1, -2, -3, -4, -5,
                        -6, -7, -8, -9,
                        -10, -11, -12, -13);
        check(hostile.left == 0 && hostile.top == 0 && hostile.right == 0);
        check(hostile.bottom == 0 && hostile.imeBottom == 0);
    }

    private static void rejectsInvalidSurfaces() {
        check(!snapshot(0, 1080, 0, 0, 0, 0, 0, 2.5f).valid);
        check(!snapshot(1920, -1, 0, 0, 0, 0, 0, 2.5f).valid);
        check(!snapshot(40_000, 1080, 0, 0, 0, 0, 0, 2.5f).valid);
        check(!snapshot(1080, 40_000, 0, 0, 0, 0, 0, 2.5f).valid);
    }

    private static void preservesAsymmetricInsetsAndCapabilities() {
        PhoneTouchUiMetricsPolicy.Snapshot value = PhoneTouchUiMetricsPolicy.normalize(
                2400, 1080, 92, 7, 31, 24, 420, 2.75f, 1.2f,
                true, true, true);
        check(value.valid);
        check(value.surfaceWidth == 2400 && value.surfaceHeight == 1080);
        check(value.safeInsetLeft == 92 && value.safeInsetTop == 7);
        check(value.safeInsetRight == 31 && value.safeInsetBottom == 24);
        check(value.imeInsetBottom == 420 && value.keyboardVisible);
        check(value.hoverSupported && value.hardwareKeyboardSupported && value.hapticsSupported);
        check(close(value.density, 2.75f) && close(value.fontScale, 1.2f));
    }

    private static void derivesStableDensityScaleWithoutImeZooming() {
        PhoneTouchUiMetricsPolicy.Snapshot hidden = snapshot(
                1920, 1080, 25, 25, 25, 25, 0, 2.5f);
        PhoneTouchUiMetricsPolicy.Snapshot shown = snapshot(
                1920, 1080, 25, 25, 25, 25, 480, 2.5f);
        check(close(hidden.contentScale, 2.5f));
        check(close(shown.contentScale, hidden.contentScale));
        check(!hidden.keyboardVisible && shown.keyboardVisible);

        PhoneTouchUiMetricsPolicy.Snapshot compact = snapshot(
                640, 360, 0, 0, 0, 0, 0, 3.0f);
        check(close(compact.contentScale, 1.15f));
        check(!compact.keyboardVisible);
        PhoneTouchUiMetricsPolicy.Snapshot expanded = snapshot(
                3200, 1800, 0, 0, 0, 0, 0, 4.0f);
        check(close(expanded.contentScale, 3.0f));
    }

    private static void clampsHostileMeasurements() {
        PhoneTouchUiMetricsPolicy.Snapshot value = PhoneTouchUiMetricsPolicy.normalize(
                100, 80, -20, 500, 500, -1, 900,
                Float.NaN, Float.POSITIVE_INFINITY, false, false, false);
        check(value.valid);
        check(value.safeInsetLeft == 0);
        check(value.safeInsetRight == 99);
        check(value.safeInsetTop == 79);
        check(value.safeInsetBottom == 0);
        check(value.imeInsetBottom == 0);
        check(close(value.density, 1.0f));
        check(close(value.fontScale, 1.0f));
        check(close(value.contentScale, 1.0f));

        PhoneTouchUiMetricsPolicy.Snapshot collapsed = snapshot(
                100, 80, 80, 70, 80, 70, 0, 1.0f);
        check(collapsed.safeInsetLeft == 80 && collapsed.safeInsetRight == 19);
        check(collapsed.safeInsetTop == 70 && collapsed.safeInsetBottom == 9);

        PhoneTouchUiMetricsPolicy.Snapshot exactlyCollapsed = snapshot(
                100, 80, 60, 20, 40, 60, 0, 1.0f);
        check(exactlyCollapsed.safeInsetLeft == 60
                && exactlyCollapsed.safeInsetRight == 39);
        check(exactlyCollapsed.safeInsetTop == 20
                && exactlyCollapsed.safeInsetBottom == 59);

        PhoneTouchUiMetricsPolicy.Snapshot bounded = PhoneTouchUiMetricsPolicy.normalize(
                1000, 800, 0, 0, 0, 0, 0,
                99.0f, -5.0f, false, false, false);
        check(close(bounded.density, 8.0f));
        check(close(bounded.fontScale, 0.5f));
    }

    private static void snapshotsHaveStableValueSemantics() {
        PhoneTouchUiMetricsPolicy.Snapshot baseline = snapshot(
                1920, 1080, 10, 20, 30, 40, 0, 2.5f);
        PhoneTouchUiMetricsPolicy.Snapshot same = snapshot(
                1920, 1080, 10, 20, 30, 40, 0, 2.5f);
        check(baseline.equals(baseline));
        check(baseline.equals(same));
        check(same.equals(baseline));
        check(baseline.hashCode() == same.hashCode());
        check(!baseline.equals(null));
        check(!baseline.equals("metrics"));
        check(!baseline.equals(snapshot(1919, 1080, 10, 20, 30, 40, 0, 2.5f)));
        check(!baseline.equals(snapshot(1920, 1079, 10, 20, 30, 40, 0, 2.5f)));
        check(!baseline.equals(snapshot(1920, 1080, 11, 20, 30, 40, 0, 2.5f)));
        check(!baseline.equals(snapshot(1920, 1080, 10, 21, 30, 40, 0, 2.5f)));
        check(!baseline.equals(snapshot(1920, 1080, 10, 20, 31, 40, 0, 2.5f)));
        check(!baseline.equals(snapshot(1920, 1080, 10, 20, 30, 41, 0, 2.5f)));
        check(!baseline.equals(snapshot(1920, 1080, 10, 20, 30, 40, 200, 2.5f)));
        check(!baseline.equals(snapshot(1920, 1080, 10, 20, 30, 40, 0, 2.6f)));
        PhoneTouchUiMetricsPolicy.Snapshot differentFont =
                PhoneTouchUiMetricsPolicy.normalize(
                        1920, 1080, 10, 20, 30, 40, 0,
                        2.5f, 1.1f, false, false, true);
        check(!baseline.equals(differentFont));
        PhoneTouchUiMetricsPolicy.Snapshot hover =
                PhoneTouchUiMetricsPolicy.normalize(
                        1920, 1080, 10, 20, 30, 40, 0,
                        2.5f, 1.0f, true, false, true);
        check(!baseline.equals(hover));
        PhoneTouchUiMetricsPolicy.Snapshot keyboard =
                PhoneTouchUiMetricsPolicy.normalize(
                        1920, 1080, 10, 20, 30, 40, 0,
                        2.5f, 1.0f, false, true, true);
        check(!baseline.equals(keyboard));
        PhoneTouchUiMetricsPolicy.Snapshot noHaptics =
                PhoneTouchUiMetricsPolicy.normalize(
                        1920, 1080, 10, 20, 30, 40, 0,
                        2.5f, 1.0f, false, false, false);
        check(!baseline.equals(noHaptics));
        check(!baseline.equals(snapshot(0, 1080, 0, 0, 0, 0, 0, 1.0f)));
    }

    private static void coversRepresentativeDeviceMatrix() {
        int[][] devices = {
                {640, 360, 0, 0, 0, 24},       // compact landscape
                {360, 640, 0, 24, 0, 24},       // compact portrait
                {2400, 1080, 92, 0, 31, 24},    // asymmetric cutout
                {2208, 1840, 0, 48, 0, 48},     // unfolded/foldable
                {1280, 720, 0, 0, 0, 0},        // low-end tablet
                {3440, 1440, 0, 0, 0, 32}       // wide desktop-touch surface
        };
        for (int[] device : devices) {
            PhoneTouchUiMetricsPolicy.Snapshot value = snapshot(
                    device[0], device[1], device[2], device[3],
                    device[4], device[5], 0, 2.5f);
            check(value.valid);
            check(value.contentScale >= 1.0f && value.contentScale <= 3.0f);
            check(value.safeInsetLeft + value.safeInsetRight < value.surfaceWidth);
            check(value.safeInsetTop + value.safeInsetBottom < value.surfaceHeight);
        }
    }

    private static void runsBoundedDeterministicPerformanceMatrix() {
        long started = System.nanoTime();
        long checksum = 0;
        for (int index = 0; index < 100_000; ++index) {
            int width = 320 + (index * 37 % 3_680);
            int height = 240 + (index * 53 % 1_920);
            int left = index % 97;
            int top = index % 61;
            PhoneTouchUiMetricsPolicy.Snapshot value = snapshot(
                    width, height, left, top, index % 43, index % 37,
                    index % Math.max(1, height), 0.5f + (index % 76) / 10.0f);
            check(value.valid);
            checksum += value.surfaceWidth + value.safeInsetLeft
                    + Math.round(value.contentScale * 100.0f);
        }
        long elapsedMillis = (System.nanoTime() - started) / 1_000_000L;
        check(checksum > 0);
        // Generous enough for shared CI, but catches accidental allocation or
        // super-linear regressions in this per-frame-adjacent normalization.
        check(elapsedMillis < 5_000L);
    }

    private static PhoneTouchUiMetricsPolicy.Snapshot snapshot(
            int width, int height, int left, int top, int right, int bottom,
            int ime, float density) {
        return PhoneTouchUiMetricsPolicy.normalize(
                width, height, left, top, right, bottom, ime,
                density, 1.0f, false, false, true);
    }

    private static boolean close(float first, float second) {
        return Math.abs(first - second) < 0.001f;
    }

    private static void check(boolean condition) {
        ++assertions;
        if (!condition) {
            throw new AssertionError("assertion " + assertions + " failed");
        }
    }
}
