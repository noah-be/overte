// SPDX-License-Identifier: Apache-2.0
#include "interface/src/metrics/NativeMetrics.h"
#include <cassert>
#include <atomic>
#include <thread>
using namespace overte::metrics;
int main() {
    LatestSample latest;
    Sample sample;
    assert(latest.read(0).producer == Producer::Unavailable);
    sample.producer = Producer::IOS;
    sample.foreground = true;
    sample.footprintAvailable = true;
    sample.footprintBytes = 123456789;
    sample.thermal = Thermal::Nominal;
    sample.lowPowerAvailable = true;
    assert(latest.publish(sample, 100));
    assert(latest.read(35100).footprintBytes == 123456789);
    assert(latest.read(35101).producer == Producer::Unavailable);
    assert(latest.read(99).producer == Producer::Unavailable);
    assert(!latest.publish(sample, 99));
    assert(latest.read(100).producer == Producer::Unavailable);
    assert(latest.publish(sample, 200));
    assert(iosFrameLimit(60, sample) == 60);
    sample.lowPower = true;
    assert(iosFrameLimit(60, sample) == 30);
    assert(iosFrameLimit(2, sample) == 2);
    sample.lowPower = false;
    sample.thermal = Thermal::Serious;
    assert(iosFrameLimit(120, sample) == 30);
    sample.thermal = Thermal::Critical;
    assert(iosFrameLimit(60, sample) == 15);
    assert(iosFrameLimit(2, sample) == 2);
    sample.thermal = Thermal::Unavailable;
    assert(iosFrameLimit(60, sample) == 30);
    sample.footprintBytes = 0;
    assert(!LatestSample::valid(sample));
    sample.footprintAvailable = false;
    assert(LatestSample::valid(sample));
    sample.thermal = static_cast<Thermal>(99);
    assert(!LatestSample::valid(sample));
    sample.thermal = Thermal::Nominal;
    sample.foreground = false;
    assert(!LatestSample::valid(sample));
    assert(latest.publish({}, 300));
    assert(latest.read(300).producer == Producer::Unavailable);
    sample = {};
    sample.producer = Producer::IOS;
    sample.foreground = true;
    sample.thermal = Thermal::Nominal;
    std::atomic<int> callbacks {0};
    setNativeMetricsChangedCallback([&] { ++callbacks; });
    assert(publishNativeSample(sample));
    assert(callbacks == 1 && latestNativeSample().thermal == Thermal::Nominal);
    std::thread writer([&] { for (int i = 0; i < 1000; ++i) { publishNativeSample(sample); } });
    setNativeMetricsChangedCallback({});
    const int afterUnregister = callbacks;
    writer.join();
    assert(callbacks == afterUnregister);
    assert(publishNativeSample({}));
    assert(latestNativeSample().producer == Producer::Unavailable);
}
