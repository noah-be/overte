// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../ui/KeyboardGeometry.h"
#include <cassert>
#include <limits>

using namespace overte::ios;
int main() {
    const KeyboardRect portrait { 0, 0, 390, 844 };
    auto result = keyboardOcclusion(portrait, { 0, 544, 390, 300 });
    assert(result.available && result.visible && result.bottomInset == 300);
    result = keyboardOcclusion(portrait, { 50, 400, 280, 220 });
    assert(result.available && result.visible && result.bottomInset == 0);
    result = keyboardOcclusion(portrait, { 50, 644, 280, 200 });
    assert(result.visible && result.bottomInset == 0); // Narrow at bottom is not docked.
    result = keyboardOcclusion(portrait, { 0, 400, 390, 220 });
    assert(result.visible && result.bottomInset == 0); // Full width but undocked.
    result = keyboardOcclusion(portrait, { 0, 844, 390, 300 });
    assert(result.available && !result.visible && result.bottomInset == 0);
    result = keyboardOcclusion(portrait, { -100, 544, 590, 500 });
    assert(result.visible && result.bottomInset == 300); // Clip overscan.
    result = keyboardOcclusion({ 20, 10, 600, 400 }, { -10, 300, 700, 400 });
    assert(result.visible && result.bottomInset == 110); // Nonzero window bounds.
    result = keyboardOcclusion({ 0, 0, 844, 390 }, { 0, 190, 844, 200 });
    assert(result.visible && result.bottomInset == 200); // Landscape, points unchanged.
    result = keyboardOcclusion(portrait, { 900, 500, 100, 400 });
    assert(result.available && !result.visible && result.bottomInset == 0);
    for (double invalid : { std::numeric_limits<double>::infinity(),
                            -std::numeric_limits<double>::infinity(),
                            std::numeric_limits<double>::quiet_NaN() }) {
        assert(!keyboardOcclusion(portrait, { invalid, 0, 390, 300 }).available);
        assert(!keyboardOcclusion(portrait, { 0, invalid, 390, 300 }).available);
        assert(!keyboardOcclusion(portrait, { 0, 0, invalid, 300 }).available);
        assert(!keyboardOcclusion(portrait, { 0, 0, 390, invalid }).available);
        assert(!keyboardOcclusion({ invalid, 0, 390, 844 }, portrait).available);
    }
    assert(!keyboardOcclusion(portrait, { 0, 544, -390, 300 }).available);
    assert(!keyboardOcclusion(portrait, { 0, 544, 390, 0 }).available);
    assert(!keyboardOcclusion({}, portrait).available);
    const double huge = std::numeric_limits<double>::max();
    assert(!keyboardOcclusion(portrait, { huge, 0, huge, 300 }).available);
}
