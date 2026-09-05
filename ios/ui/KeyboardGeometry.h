// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <algorithm>
#include <cmath>

namespace overte::ios {

// UIKit points, already converted to the selected window's coordinate space.
struct KeyboardRect { double x, y, width, height; };
struct KeyboardOcclusion {
    bool available { false };
    bool visible { false };
    double bottomInset { 0.0 };
};

inline bool validKeyboardRect(KeyboardRect rect) {
    return std::isfinite(rect.x) && std::isfinite(rect.y) &&
        std::isfinite(rect.width) && std::isfinite(rect.height) &&
        rect.width > 0.0 && rect.height > 0.0 &&
        std::isfinite(rect.x + rect.width) && std::isfinite(rect.y + rect.height);
}

inline KeyboardOcclusion keyboardOcclusion(KeyboardRect window, KeyboardRect keyboard) {
    if (!validKeyboardRect(window) || !validKeyboardRect(keyboard)) {
        return {};
    }
    const double left = std::max(window.x, keyboard.x);
    const double top = std::max(window.y, keyboard.y);
    const double right = std::min(window.x + window.width, keyboard.x + keyboard.width);
    const double bottom = std::min(window.y + window.height, keyboard.y + keyboard.height);
    if (right <= left || bottom <= top) {
        return { true, false, 0.0 };
    }
    // A floating/undocked keyboard can be visible without reserving a full-width
    // strip. Do not multiply points by display density or subtract safe area here.
    constexpr double tolerance = 0.5;
    const bool docked = left <= window.x + tolerance &&
        right >= window.x + window.width - tolerance &&
        bottom >= window.y + window.height - tolerance;
    return { true, true, docked ? bottom - top : 0.0 };
}

} // namespace overte::ios
