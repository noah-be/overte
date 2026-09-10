// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../../performance/NativeMetrics.h"
#include "../../performance/SharedMetricsPublisher.h"
#include "../../../interface/src/metrics/NativeMetrics.h"
#include <cassert>
#include <limits>
using namespace overte::ios;
int main() {
    NativeMetrics unavailable;
    unavailable.footprintBytes = 999; // failed samples must not leak stale data
    assert(formatNativeMetrics(unavailable) ==
        "footprint_bytes=unavailable thermal=unknown low_power=unavailable energy_joules=unavailable");
    NativeMetrics measured { true, 123456, ThermalState::Serious, true, true };
    assert(publishNativeMetrics(measured, true));
    auto shared = overte::metrics::latestNativeSample();
    assert(shared.producer == overte::metrics::Producer::IOS && shared.foreground);
    assert(shared.footprintBytes == measured.footprintBytes && shared.lowPowerAvailable && shared.lowPower);
    assert(shared.thermal == overte::metrics::Thermal::Serious);
    assert(overte::metrics::iosFrameLimit(60, shared) == 30);
    assert(publishNativeMetrics(measured, false));
    assert(overte::metrics::latestNativeSample().producer == overte::metrics::Producer::Unavailable);
    assert(publishNativeMetrics(unavailable, true));
    shared = overte::metrics::latestNativeSample();
    assert(!shared.footprintAvailable && shared.footprintBytes == 0 && !shared.lowPowerAvailable);
    assert(shared.thermal == overte::metrics::Thermal::Unavailable);
    assert(overte::metrics::iosFrameLimit(60, shared) == 30);
    NativeMetrics invalid { true, 0, ThermalState::Nominal, false, true };
    assert(!publishNativeMetrics(invalid, true));
    assert(overte::metrics::latestNativeSample().producer == overte::metrics::Producer::Unavailable);
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
    assert(previewFrameLimit(ThermalState::Unknown, false, false) == 30);
    assert(previewFrameLimit(ThermalState::Nominal, true, false) == 30);
    assert(previewFrameLimit(ThermalState::Nominal, false, true) == 30);
    assert(previewFrameLimit(ThermalState::Serious, false, false) == 30);
    assert(previewFrameLimit(ThermalState::Critical, true, true) == 15);
}
