// SPDX-License-Identifier: Apache-2.0
#pragma once

#if defined(ANDROID_APP_PHONE_INTERFACE)

#include <cstdint>

namespace phone_framebuffer_telemetry {

struct Snapshot {
    uint64_t primaryRecreateCount { 0 };
    uint64_t resolveRecreateCount { 0 };
    uint64_t primarySizeSamples { 0 };
    uint64_t resolveSizeSamples { 0 };
};

void recordPrimaryRecreate(uint32_t width, uint32_t height, uint32_t samples);
void recordResolveRecreate(uint32_t width, uint32_t height);
Snapshot snapshot();

constexpr uint64_t packSizeSamples(uint32_t width, uint32_t height, uint32_t samples) noexcept {
    return (static_cast<uint64_t>(width) << 40) |
        (static_cast<uint64_t>(height) << 16) |
        static_cast<uint64_t>(samples & 0xFFFFU);
}

constexpr uint32_t unpackWidth(uint64_t packed) noexcept { return static_cast<uint32_t>(packed >> 40); }
constexpr uint32_t unpackHeight(uint64_t packed) noexcept { return static_cast<uint32_t>((packed >> 16) & 0xFFFFFFU); }
constexpr uint32_t unpackSamples(uint64_t packed) noexcept { return static_cast<uint32_t>(packed & 0xFFFFU); }

} // namespace phone_framebuffer_telemetry

#endif
