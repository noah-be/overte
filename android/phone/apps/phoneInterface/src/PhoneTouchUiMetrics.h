//
// Defensive native boundary for Android touch UI surface measurements.
//

#pragma once

#include <algorithm>
#include <cmath>

namespace phone {

struct TouchUiMetrics {
    static constexpr int MAX_SURFACE_EXTENT { 32768 };

    bool valid { false };
    int surfaceWidth { 0 };
    int surfaceHeight { 0 };
    int safeInsetLeft { 0 };
    int safeInsetTop { 0 };
    int safeInsetRight { 0 };
    int safeInsetBottom { 0 };
    int imeInsetBottom { 0 };
    float density { 1.0f };
    float fontScale { 1.0f };
    float contentScale { 1.0f };
    bool keyboardVisible { false };
    bool hoverSupported { false };
    bool hardwareKeyboardSupported { false };
    bool hapticsSupported { false };

    static TouchUiMetrics fromUntrusted(
            int width,
            int height,
            int left,
            int top,
            int right,
            int bottom,
            int imeBottom,
            float rawDensity,
            float rawFontScale,
            float rawContentScale,
            bool rawKeyboardVisible,
            bool rawHoverSupported,
            bool rawHardwareKeyboardSupported,
            bool rawHapticsSupported) {
        TouchUiMetrics result;
        if (width <= 0 || height <= 0
                || width > MAX_SURFACE_EXTENT || height > MAX_SURFACE_EXTENT) {
            return result;
        }

        result.valid = true;
        result.surfaceWidth = width;
        result.surfaceHeight = height;
        result.safeInsetLeft = bounded(left, 0, width - 1);
        result.safeInsetTop = bounded(top, 0, height - 1);
        result.safeInsetRight = bounded(right, 0,
                width - result.safeInsetLeft - 1);
        result.safeInsetBottom = bounded(bottom, 0,
                height - result.safeInsetTop - 1);
        result.imeInsetBottom = bounded(imeBottom, 0,
                height - result.safeInsetTop - 1);
        result.density = boundedFinite(rawDensity, 1.0f, 0.5f, 8.0f);
        result.fontScale = boundedFinite(rawFontScale, 1.0f, 0.5f, 2.0f);
        result.contentScale = boundedFinite(rawContentScale, 1.0f, 1.0f, 3.0f);
        result.keyboardVisible = rawKeyboardVisible
                && result.imeInsetBottom > result.safeInsetBottom;
        result.hoverSupported = rawHoverSupported;
        result.hardwareKeyboardSupported = rawHardwareKeyboardSupported;
        result.hapticsSupported = rawHapticsSupported;
        return result;
    }

private:
    static int bounded(int value, int minimum, int maximum) {
        return std::max(minimum, std::min(maximum, value));
    }

    static float boundedFinite(float value, float fallback,
            float minimum, float maximum) {
        const float finiteValue = std::isfinite(value) ? value : fallback;
        return std::max(minimum, std::min(maximum, finiteValue));
    }
};

} // namespace phone
