#include <cmath>
#include <iostream>
#include <limits>

#include "PhoneTouchUiMetrics.h"

namespace {

int failures { 0 };

void expect(bool condition, const char* message) {
    if (!condition) {
        ++failures;
        std::cerr << "expectation failed: " << message << '\n';
    }
}

} // namespace

int main() {
    using phone::TouchUiMetrics;

    const auto invalidWidth = TouchUiMetrics::fromUntrusted(
        0, 1080, 0, 0, 0, 0, 0, 2.5f, 1.0f, 2.5f,
        false, false, false, true);
    const auto invalidHeight = TouchUiMetrics::fromUntrusted(
        1080, -1, 0, 0, 0, 0, 0, 2.5f, 1.0f, 2.5f,
        false, false, false, true);
    const auto excessiveWidth = TouchUiMetrics::fromUntrusted(
        32769, 1080, 0, 0, 0, 0, 0, 2.5f, 1.0f, 2.5f,
        false, false, false, true);
    const auto excessiveHeight = TouchUiMetrics::fromUntrusted(
        1080, 32769, 0, 0, 0, 0, 0, 2.5f, 1.0f, 2.5f,
        false, false, false, true);
    expect(!invalidWidth.valid, "zero-width surfaces are rejected");
    expect(!invalidHeight.valid, "negative-height surfaces are rejected");
    expect(!excessiveWidth.valid, "excessive-width surfaces are rejected");
    expect(!excessiveHeight.valid, "excessive-height surfaces are rejected");

    const auto asymmetric = TouchUiMetrics::fromUntrusted(
        2400, 1080, 92, 7, 31, 24, 420, 2.75f, 1.2f, 2.75f,
        true, true, true, true);
    expect(asymmetric.valid, "representative surface is valid");
    expect(asymmetric.safeInsetLeft == 92, "left cutout survives JNI");
    expect(asymmetric.safeInsetRight == 31, "right cutout survives JNI");
    expect(asymmetric.imeInsetBottom == 420, "IME inset survives JNI");
    expect(asymmetric.keyboardVisible, "visible IME is retained");
    expect(asymmetric.hoverSupported, "hybrid hover capability survives JNI");
    expect(asymmetric.hardwareKeyboardSupported,
        "hardware keyboard capability survives JNI");
    expect(asymmetric.hapticsSupported, "haptics capability survives JNI");

    const auto hostile = TouchUiMetrics::fromUntrusted(
        100, 80, -1, 500, 500, -1, 900,
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -100.0f, true, false, false, false);
    expect(hostile.valid, "bounded hostile surface remains usable");
    expect(hostile.safeInsetLeft == 0, "negative left inset is clamped");
    expect(hostile.safeInsetTop == 79, "top inset is bounded to surface");
    expect(hostile.safeInsetRight == 99, "trailing inset leaves one pixel");
    expect(hostile.safeInsetBottom == 0, "trailing bottom inset leaves one pixel");
    expect(hostile.imeInsetBottom == 0, "IME cannot overlap protected top");
    expect(std::abs(hostile.density - 1.0f) < 0.001f,
        "non-finite density uses fallback");
    expect(std::abs(hostile.fontScale - 1.0f) < 0.001f,
        "non-finite font scale uses fallback");
    expect(std::abs(hostile.contentScale - 1.0f) < 0.001f,
        "negative content scale is clamped");
    expect(!hostile.keyboardVisible, "invalid IME visibility fails closed");

    const auto boundedScales = TouchUiMetrics::fromUntrusted(
        1000, 800, 0, 0, 0, 40, 40,
        99.0f, -5.0f, 99.0f, true, false, false, false);
    expect(std::abs(boundedScales.density - 8.0f) < 0.001f,
        "density has an upper bound");
    expect(std::abs(boundedScales.fontScale - 0.5f) < 0.001f,
        "font scale has a lower bound");
    expect(std::abs(boundedScales.contentScale - 3.0f) < 0.001f,
        "content scale has an upper bound");
    expect(!boundedScales.keyboardVisible,
        "equal IME and safe insets are not a visible keyboard");

    const auto suppressedKeyboard = TouchUiMetrics::fromUntrusted(
        1000, 800, 0, 0, 0, 20, 300,
        1.0f, 1.0f, 1.0f, false, false, false, false);
    expect(!suppressedKeyboard.keyboardVisible,
        "native visibility cannot be invented from the inset alone");

    return failures == 0 ? 0 : 1;
}
