//
//  MacOSGPUTextureReadiness.h
//  libraries/shared/src
//
//  Copyright 2026 Overte e.V.
//  SPDX-License-Identifier: Apache-2.0
//

#pragma once

#include <cstdint>
#include <string_view>

namespace macos::gpu_texture_readiness {

constexpr bool usesStableAllocationFallback(std::string_view renderer) {
    return renderer.find("Apple Software Renderer") != std::string_view::npos;
}

constexpr bool isComplete(
        std::int64_t stabilityCount,
        std::int64_t requiredStabilityCount,
        std::int64_t allocatedBytes,
        std::int64_t populatedBytes,
        std::int64_t pendingTransferBytes,
        std::string_view renderer) {
    if (stabilityCount < requiredStabilityCount || pendingTransferBytes != 0) {
        return false;
    }
    return allocatedBytes == populatedBytes || usesStableAllocationFallback(renderer);
}

} // namespace macos::gpu_texture_readiness
