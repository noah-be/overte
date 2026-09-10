// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <algorithm>
#include <cmath>

namespace overte::ios {
struct PreviewCamera {
    float yaw { 0.0f };
    float pitch { -0.28f };
    float zoom { 1.0f };
    void reset() noexcept { *this = PreviewCamera {}; }
    bool rotate(double deltaYaw, double deltaPitch) noexcept {
        if (!std::isfinite(deltaYaw) || !std::isfinite(deltaPitch)) { return false; }
        yaw = static_cast<float>(std::remainder(static_cast<double>(yaw) + deltaYaw, 6.283185307179586));
        pitch = static_cast<float>(std::clamp(static_cast<double>(pitch) + deltaPitch, -1.1, 0.35));
        return true;
    }
    bool scale(double factor) noexcept {
        if (!std::isfinite(factor) || factor <= 0) { return false; }
        zoom = static_cast<float>(std::clamp(static_cast<double>(zoom) * factor, 0.55, 1.8));
        return true;
    }
};
} // namespace overte::ios
