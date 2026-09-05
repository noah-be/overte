// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "SharedMetricsPublisher.h"
#include "../../interface/src/metrics/NativeMetrics.h"

namespace overte::ios {
bool publishNativeMetrics(const NativeMetrics& native, bool foreground) {
    metrics::Sample sample;
    if (foreground) {
        sample.producer = metrics::Producer::IOS;
        sample.foreground = true;
        sample.footprintAvailable = native.footprintAvailable;
        sample.footprintBytes = native.footprintAvailable ? native.footprintBytes : 0;
        sample.lowPowerAvailable = native.lowPowerAvailable;
        sample.lowPower = native.lowPowerAvailable && native.lowPower;
        switch (native.thermal) {
            case ThermalState::Nominal: sample.thermal = metrics::Thermal::Nominal; break;
            case ThermalState::Fair: sample.thermal = metrics::Thermal::Fair; break;
            case ThermalState::Serious: sample.thermal = metrics::Thermal::Serious; break;
            case ThermalState::Critical: sample.thermal = metrics::Thermal::Critical; break;
            default: sample.thermal = metrics::Thermal::Unavailable; break;
        }
    }
    const bool accepted = metrics::publishNativeSample(sample);
    recordNativeMetrics(accepted && foreground ? native : NativeMetrics {});
    return accepted;
}
}
