// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../../performance/NativeMetrics.h"
#include "../../../interface/src/metrics/NativeMetrics.h"
#include <QGuiApplication>
#include <QTimer>
#include <cassert>

namespace { int samples = 0; }
namespace overte::ios {
// Native OS query substituted only in this test; real Qt startup wiring runs.
NativeMetrics sampleNativeMetrics() noexcept {
    ++samples;
    return { true, 1234, ThermalState::Fair, false, true };
}
}
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    QCoreApplication::processEvents(); // registered startup installation
    const auto timers = app.findChildren<QTimer*>();
    assert(timers.size() == 1 && timers[0]->interval() == 30000);
    app.applicationStateChanged(Qt::ApplicationActive);
    assert(timers[0]->isActive());
    assert(overte::ios::latestNativeMetrics().footprintBytes == 1234);
    assert(overte::metrics::latestNativeSample().footprintBytes == 1234);
    assert(overte::metrics::latestNativeSample().lowPowerAvailable);
    const auto activeSamples = samples;
    app.applicationStateChanged(Qt::ApplicationSuspended);
    assert(!timers[0]->isActive());
    const auto suspended = overte::ios::latestNativeMetrics();
    assert(!suspended.footprintAvailable && suspended.footprintBytes == 0);
    assert(suspended.thermal == overte::ios::ThermalState::Unknown);
    assert(overte::metrics::latestNativeSample().producer == overte::metrics::Producer::Unavailable);
    assert(samples == activeSamples);
    app.applicationStateChanged(Qt::ApplicationActive);
    assert(samples == activeSamples + 1 && timers[0]->isActive());
}
