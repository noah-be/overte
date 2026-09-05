// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "NativeMetrics.h"
#include <mutex>

namespace overte::ios {
namespace {
std::mutex metricsMutex;
NativeMetrics latest;
}
void recordNativeMetrics(const NativeMetrics& metrics) {
    std::lock_guard guard(metricsMutex);
    latest = metrics;
    if (!latest.footprintAvailable) { latest.footprintBytes = 0; }
    if (!latest.lowPowerAvailable) { latest.lowPower = false; }
}
NativeMetrics latestNativeMetrics() {
    std::lock_guard guard(metricsMutex);
    return latest;
}
std::string formatNativeMetrics(const NativeMetrics& metrics) {
    const char* thermal = "unknown";
    switch (metrics.thermal) {
        case ThermalState::Unknown: break;
        case ThermalState::Nominal: thermal = "nominal"; break;
        case ThermalState::Fair: thermal = "fair"; break;
        case ThermalState::Serious: thermal = "serious"; break;
        case ThermalState::Critical: thermal = "critical"; break;
    }
    return std::string("footprint_bytes=") +
        (metrics.footprintAvailable ? std::to_string(metrics.footprintBytes) : "unavailable") +
        " thermal=" + thermal + " low_power=" +
        (!metrics.lowPowerAvailable ? "unavailable" : metrics.lowPower ? "true" : "false") +
        " energy_joules=unavailable";
}
} // namespace overte::ios
