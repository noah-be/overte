// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../../performance/MemoryPressurePolicy.h"
#include <cassert>
using namespace overte::ios;
int main() {
    MemoryPressurePolicy policy;
    NativeMetrics metrics;
    auto result = policy.update(metrics);
    assert(!result.purgeUnused && !result.limitDownloads);
    metrics.availableMemoryAvailable = true;
    metrics.availableMemoryBytes = MemoryPressurePolicy::WARNING_HEADROOM + 1;
    assert(!policy.update(metrics).limitDownloads);
    metrics.availableMemoryBytes = MemoryPressurePolicy::WARNING_HEADROOM;
    result = policy.update(metrics);
    assert(result.level == MemoryPressureLevel::Warning && result.purgeUnused && result.limitDownloads);
    assert(!policy.update(metrics).purgeUnused);
    metrics.availableMemoryBytes = MemoryPressurePolicy::CRITICAL_HEADROOM + 1;
    assert(policy.update(metrics).level == MemoryPressureLevel::Warning);
    metrics.availableMemoryBytes = MemoryPressurePolicy::CRITICAL_HEADROOM;
    result = policy.update(metrics);
    assert(result.level == MemoryPressureLevel::Critical && result.purgeUnused);
    metrics.availableMemoryBytes = 0; // zero is a real critical reading
    result = policy.update(metrics);
    assert(result.level == MemoryPressureLevel::Critical && !result.purgeUnused);
    assert(!policy.update(metrics).purgeUnused);
    result = policy.update({}); // invalid data cannot lift pressure
    assert(result.level == MemoryPressureLevel::Critical && result.limitDownloads);
    metrics.availableMemoryBytes = MemoryPressurePolicy::RECOVERY_HEADROOM;
    assert(policy.update(metrics).limitDownloads);
    assert(policy.update(metrics).limitDownloads);
    policy.update({}); // interrupted recovery starts again
    assert(policy.update(metrics).limitDownloads);
    assert(policy.update(metrics).limitDownloads);
    assert(!policy.update(metrics).limitDownloads);
    assert(policy.update(metrics, true).purgeUnused);
    assert(policy.update(metrics).limitDownloads);
    assert(policy.update(metrics).limitDownloads);
    assert(!policy.update(metrics).limitDownloads);
    // Device headroom takes precedence over a desktop-sized footprint.
    metrics.footprintAvailable = true;
    metrics.footprintBytes = 4ULL * 1024 * MemoryPressurePolicy::MIB;
    assert(!policy.update(metrics).limitDownloads);
    metrics.availableMemoryAvailable = false;
    result = policy.update(metrics);
    assert(result.level == MemoryPressureLevel::Critical && result.purgeUnused);
    // Native sample storage normalizes failed headroom measurements.
    metrics.availableMemoryBytes = 999;
    recordNativeMetrics(metrics);
    assert(!latestNativeMetrics().availableMemoryAvailable && latestNativeMetrics().availableMemoryBytes == 0);
    metrics.availableMemoryAvailable = true;
    metrics.availableMemoryBytes = 0;
    recordNativeMetrics(metrics);
    assert(latestNativeMetrics().availableMemoryAvailable && latestNativeMetrics().availableMemoryBytes == 0);
}
