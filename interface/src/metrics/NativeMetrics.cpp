// SPDX-License-Identifier: Apache-2.0
#include "NativeMetrics.h"
#include <chrono>
#include <utility>

namespace {
overte::metrics::LatestSample latest;
std::mutex callbackMutex;
std::function<void()> changed;
std::uint64_t now() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
}
bool overte::metrics::publishNativeSample(const Sample& sample) {
    const bool valid = latest.publish(sample, now());
    std::lock_guard<std::mutex> lock(callbackMutex);
    if (changed) { changed(); } // Only enqueue; never reenter callback registry.
    return valid;
}
overte::metrics::Sample overte::metrics::latestNativeSample() { return latest.read(now()); }
void overte::metrics::setNativeMetricsChangedCallback(std::function<void()> callback) {
    std::lock_guard<std::mutex> lock(callbackMutex);
    changed = std::move(callback);
}
