package org.overte.phone;

import java.util.Objects;

/**
 * Normalizes untrusted Android window/input measurements before they cross JNI.
 * This class intentionally has no Android dependencies so the complete device
 * matrix can run on every host and in mutation/coverage jobs.
 */
public final class PhoneTouchUiMetricsPolicy {
    static final int MAX_SURFACE_EXTENT = 32_768;
    static final float MIN_DENSITY = 0.5f;
    static final float MAX_DENSITY = 8.0f;
    static final float MIN_FONT_SCALE = 0.5f;
    static final float MAX_FONT_SCALE = 2.0f;
    static final float MIN_CONTENT_SCALE = 1.0f;
    static final float MAX_CONTENT_SCALE = 3.0f;
    static final float BASELINE_CONTENT_WIDTH = 480.0f;
    static final float BASELINE_CONTENT_HEIGHT = 320.0f;

    private PhoneTouchUiMetricsPolicy() {
    }

    /**
     * Separates the pre-API-30 IME contribution from persistent navigation,
     * gesture, and cutout protection. All arguments are raw pixel insets.
     */
    public static LegacyInsets normalizeLegacyInsets(
            int systemLeft,
            int systemTop,
            int systemRight,
            int systemBottom,
            int stableBottom,
            int mandatoryLeft,
            int mandatoryTop,
            int mandatoryRight,
            int mandatoryBottom,
            int cutoutLeft,
            int cutoutTop,
            int cutoutRight,
            int cutoutBottom) {
        int persistentBottom = Math.max(0, stableBottom);
        int normalizedSystemBottom = Math.max(0, systemBottom);
        int imeBottom = normalizedSystemBottom > persistentBottom
                ? normalizedSystemBottom : 0;
        return new LegacyInsets(
                maximumNonNegative(systemLeft, mandatoryLeft, cutoutLeft),
                maximumNonNegative(systemTop, mandatoryTop, cutoutTop),
                maximumNonNegative(systemRight, mandatoryRight, cutoutRight),
                maximumNonNegative(
                        Math.min(normalizedSystemBottom, persistentBottom),
                        mandatoryBottom,
                        cutoutBottom),
                imeBottom);
    }

    public static Snapshot normalize(
            int surfaceWidth,
            int surfaceHeight,
            int safeInsetLeft,
            int safeInsetTop,
            int safeInsetRight,
            int safeInsetBottom,
            int imeInsetBottom,
            float density,
            float fontScale,
            boolean hoverSupported,
            boolean hardwareKeyboardSupported,
            boolean hapticsSupported) {
        if (surfaceWidth <= 0 || surfaceHeight <= 0
                || surfaceWidth > MAX_SURFACE_EXTENT
                || surfaceHeight > MAX_SURFACE_EXTENT) {
            return Snapshot.invalid();
        }

        int left = clamp(safeInsetLeft, 0, surfaceWidth - 1);
        int top = clamp(safeInsetTop, 0, surfaceHeight - 1);
        int right = clamp(safeInsetRight, 0, surfaceWidth - 1);
        int bottom = clamp(safeInsetBottom, 0, surfaceHeight - 1);

        // Malformed or transient inset combinations must never collapse the
        // complete Qt surface. Reduce the trailing side deterministically.
        if (left + right >= surfaceWidth) {
            right = Math.max(0, surfaceWidth - left - 1);
        }
        if (top + bottom >= surfaceHeight) {
            bottom = Math.max(0, surfaceHeight - top - 1);
        }

        int ime = clamp(imeInsetBottom, 0, surfaceHeight - top - 1);
        float normalizedDensity = clampFinite(density, 1.0f, MIN_DENSITY, MAX_DENSITY);
        float normalizedFontScale = clampFinite(
                fontScale, 1.0f, MIN_FONT_SCALE, MAX_FONT_SCALE);

        int usableWidth = Math.max(1, surfaceWidth - left - right);
        int usableHeight = Math.max(1, surfaceHeight - top - bottom);
        float widthLimit = usableWidth / BASELINE_CONTENT_WIDTH;
        float heightLimit = usableHeight / BASELINE_CONTENT_HEIGHT;
        float scale = Math.min(normalizedDensity, Math.min(widthLimit, heightLimit));
        scale = clampFinite(scale, MIN_CONTENT_SCALE,
                MIN_CONTENT_SCALE, MAX_CONTENT_SCALE);
        // Avoid layout churn from insignificant display-metric jitter.
        scale = Math.round(scale * 20.0f) / 20.0f;

        boolean keyboardVisible = ime > bottom;
        return new Snapshot(
                true,
                surfaceWidth,
                surfaceHeight,
                left,
                top,
                right,
                bottom,
                ime,
                normalizedDensity,
                normalizedFontScale,
                scale,
                keyboardVisible,
                hoverSupported,
                hardwareKeyboardSupported,
                hapticsSupported);
    }

    private static int clamp(int value, int minimum, int maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    private static int maximumNonNegative(int first, int second, int third) {
        return Math.max(0, Math.max(first, Math.max(second, third)));
    }

    private static float clampFinite(
            float value, float fallback, float minimum, float maximum) {
        float finiteValue = Float.isFinite(value) ? value : fallback;
        return Math.max(minimum, Math.min(maximum, finiteValue));
    }

    public static final class LegacyInsets {
        public final int left;
        public final int top;
        public final int right;
        public final int bottom;
        public final int imeBottom;

        private LegacyInsets(int left, int top, int right, int bottom, int imeBottom) {
            this.left = left;
            this.top = top;
            this.right = right;
            this.bottom = bottom;
            this.imeBottom = imeBottom;
        }
    }

    public static final class Snapshot {
        public final boolean valid;
        public final int surfaceWidth;
        public final int surfaceHeight;
        public final int safeInsetLeft;
        public final int safeInsetTop;
        public final int safeInsetRight;
        public final int safeInsetBottom;
        public final int imeInsetBottom;
        public final float density;
        public final float fontScale;
        public final float contentScale;
        public final boolean keyboardVisible;
        public final boolean hoverSupported;
        public final boolean hardwareKeyboardSupported;
        public final boolean hapticsSupported;

        private Snapshot(
                boolean valid,
                int surfaceWidth,
                int surfaceHeight,
                int safeInsetLeft,
                int safeInsetTop,
                int safeInsetRight,
                int safeInsetBottom,
                int imeInsetBottom,
                float density,
                float fontScale,
                float contentScale,
                boolean keyboardVisible,
                boolean hoverSupported,
                boolean hardwareKeyboardSupported,
                boolean hapticsSupported) {
            this.valid = valid;
            this.surfaceWidth = surfaceWidth;
            this.surfaceHeight = surfaceHeight;
            this.safeInsetLeft = safeInsetLeft;
            this.safeInsetTop = safeInsetTop;
            this.safeInsetRight = safeInsetRight;
            this.safeInsetBottom = safeInsetBottom;
            this.imeInsetBottom = imeInsetBottom;
            this.density = density;
            this.fontScale = fontScale;
            this.contentScale = contentScale;
            this.keyboardVisible = keyboardVisible;
            this.hoverSupported = hoverSupported;
            this.hardwareKeyboardSupported = hardwareKeyboardSupported;
            this.hapticsSupported = hapticsSupported;
        }

        private static Snapshot invalid() {
            return new Snapshot(false, 0, 0, 0, 0, 0, 0, 0,
                    1.0f, 1.0f, 1.0f, false, false, false, false);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Snapshot)) {
                return false;
            }
            Snapshot snapshot = (Snapshot) other;
            return valid == snapshot.valid
                    && surfaceWidth == snapshot.surfaceWidth
                    && surfaceHeight == snapshot.surfaceHeight
                    && safeInsetLeft == snapshot.safeInsetLeft
                    && safeInsetTop == snapshot.safeInsetTop
                    && safeInsetRight == snapshot.safeInsetRight
                    && safeInsetBottom == snapshot.safeInsetBottom
                    && imeInsetBottom == snapshot.imeInsetBottom
                    && Float.compare(density, snapshot.density) == 0
                    && Float.compare(fontScale, snapshot.fontScale) == 0
                    // Both derived fields are determined by values already
                    // compared above: contentScale by geometry/density and
                    // keyboardVisible by IME/persistent bottom insets.
                    && hoverSupported == snapshot.hoverSupported
                    && hardwareKeyboardSupported == snapshot.hardwareKeyboardSupported
                    && hapticsSupported == snapshot.hapticsSupported;
        }

        @Override
        public int hashCode() {
            return Objects.hash(valid, surfaceWidth, surfaceHeight,
                    safeInsetLeft, safeInsetTop, safeInsetRight, safeInsetBottom,
                    imeInsetBottom, density, fontScale, contentScale,
                    keyboardVisible, hoverSupported,
                    hardwareKeyboardSupported, hapticsSupported);
        }
    }
}
