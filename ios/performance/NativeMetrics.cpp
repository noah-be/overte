// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "NativeMetrics.h"

namespace overte::ios {
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
        " thermal=" + thermal + " low_power=" + (metrics.lowPower ? "true" : "false") +
        " energy_joules=unavailable";
}
} // namespace overte::ios
