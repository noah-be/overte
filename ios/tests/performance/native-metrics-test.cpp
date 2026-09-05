// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../../performance/NativeMetrics.h"
#include <cassert>
#include <limits>
using namespace overte::ios;
int main() {
    NativeMetrics unavailable;
    unavailable.footprintBytes = 999; // failed samples must not leak stale data
    assert(formatNativeMetrics(unavailable) ==
        "footprint_bytes=unavailable thermal=unknown low_power=false energy_joules=unavailable");
    NativeMetrics measured { true, 123456, ThermalState::Serious, true };
    recordNativeMetrics(measured);
    assert(latestNativeMetrics().footprintBytes == 123456);
    recordNativeMetrics(unavailable);
    assert(!latestNativeMetrics().footprintAvailable && latestNativeMetrics().footprintBytes == 0);
    assert(formatNativeMetrics(measured) ==
        "footprint_bytes=123456 thermal=serious low_power=true energy_joules=unavailable");
    measured.footprintBytes = std::numeric_limits<std::uint64_t>::max();
    measured.thermal = static_cast<ThermalState>(999);
    assert(formatNativeMetrics(measured).size() < 160);
    assert(formatNativeMetrics(measured).find("thermal=unknown") != std::string::npos);
    assert(previewFrameLimit(ThermalState::Nominal, false, false) == 60);
    assert(previewFrameLimit(ThermalState::Nominal, true, false) == 30);
    assert(previewFrameLimit(ThermalState::Nominal, false, true) == 30);
    assert(previewFrameLimit(ThermalState::Serious, false, false) == 30);
    assert(previewFrameLimit(ThermalState::Critical, true, true) == 15);
}
