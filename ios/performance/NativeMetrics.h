// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <string>

namespace overte::ios {
enum class ThermalState { Unknown, Nominal, Fair, Serious, Critical };
struct NativeMetrics {
    bool footprintAvailable { false };
    std::uint64_t footprintBytes { 0 };
    ThermalState thermal { ThermalState::Unknown };
    bool lowPower { false };
    // No public process-energy counter is sampled. Never substitute device
    // battery percentage, elapsed time, or CPU load for process joules.
};
NativeMetrics sampleNativeMetrics() noexcept;
std::string formatNativeMetrics(const NativeMetrics& metrics);
// Keep a single in-process sample. Export/renderer consumers require the Shared
// metrics contract; PX-16 does not allow arbitrary numeric diagnostic strings.
void recordNativeMetrics(const NativeMetrics& metrics);
NativeMetrics latestNativeMetrics();
constexpr int previewFrameLimit(ThermalState thermal, bool lowPower, bool reduceMotion) noexcept {
    if (thermal == ThermalState::Critical) { return 15; }
    if (thermal == ThermalState::Serious || lowPower || reduceMotion) { return 30; }
    return 60;
}
} // namespace overte::ios
