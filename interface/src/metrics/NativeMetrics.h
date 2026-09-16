// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <algorithm>
#include <cstdint>
#include <functional>
#include <mutex>

namespace overte { namespace metrics {
enum class Producer { Unavailable, Phone, Pico, IOS };
enum class Thermal { Unavailable, Nominal, Fair, Serious, Critical };
struct Sample {
    Producer producer { Producer::Unavailable };
    bool foreground { false };
    bool footprintAvailable { false };
    std::uint64_t footprintBytes { 0 }; // physical PROCESS footprint, never total RAM
    Thermal thermal { Thermal::Unavailable };
    bool lowPowerAvailable { false };
    bool lowPower { false };
    // No invented process-energy counter. Battery percentage is not joules.
};

// One bounded sample. Bounds are format/availability guards, not device budgets.
class LatestSample {
public:
    static constexpr std::uint64_t MAX_AGE_MS = 35000;
    bool publish(const Sample& sample, std::uint64_t now) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (now < _lastClock || !valid(sample)) { _value = {}; _valid = false; return false; }
        _value = sample;
        _observed = _lastClock = now;
        _valid = true;
        return true;
    }
    Sample read(std::uint64_t now) const {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!_valid || now < _observed || now - _observed > MAX_AGE_MS) { return {}; }
        return _value;
    }
    static bool valid(const Sample& s) {
        if (s.producer < Producer::Unavailable || s.producer > Producer::IOS ||
            s.thermal < Thermal::Unavailable || s.thermal > Thermal::Critical) { return false; }
        if (s.footprintAvailable ? (s.footprintBytes == 0 || s.footprintBytes > (std::uint64_t(1) << 50))
                                 : s.footprintBytes != 0) { return false; }
        if (!s.lowPowerAvailable && s.lowPower) { return false; }
        if (!s.foreground && (s.footprintAvailable || s.thermal != Thermal::Unavailable || s.lowPowerAvailable)) { return false; }
        if (s.producer == Producer::Unavailable && s.foreground) { return false; }
        return true;
    }
private:
    mutable std::mutex _mutex;
    Sample _value;
    std::uint64_t _observed { 0 }, _lastClock { 0 };
    bool _valid { false };
};

inline int iosFrameLimit(int requested, const Sample& sample) {
    if (sample.producer != Producer::IOS || !sample.foreground || sample.thermal == Thermal::Unavailable) {
        return std::min(requested, 30); // unavailable is not nominal evidence
    }
    if (sample.thermal == Thermal::Critical) { return std::min(requested, 15); }
    if (sample.thermal == Thermal::Serious || (sample.lowPowerAvailable && sample.lowPower)) {
        return std::min(requested, 30);
    }
    return requested;
}

// Native owners publish typed values only; General owns callback registration.
bool publishNativeSample(const Sample& sample);
Sample latestNativeSample();
void setNativeMetricsChangedCallback(std::function<void()> callback);
} }
