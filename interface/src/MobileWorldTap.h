// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cmath>
#include <cstdint>

// A tap is recognized only after its physical release. Drags, holds, multiple
// contacts and touches owned by UI/locomotion controls cannot become clicks.
class MobileWorldTap {
public:
    void cancel() { _active = false; }
    void begin(int id, double x, double y, uint64_t timestamp, bool eligible) {
        _active = eligible && std::isfinite(x) && std::isfinite(y);
        _id = id; _x = x; _y = y; _timestamp = timestamp;
    }
    void update(int id, double x, double y, uint64_t timestamp, bool eligible) {
        if (!_active || !eligible || id != _id || !std::isfinite(x) || !std::isfinite(y)
                || timestamp < _timestamp || timestamp - _timestamp > 350
                || std::hypot(x - _x, y - _y) > 8.0) {
            cancel();
        }
    }
    bool release(int id, double x, double y, uint64_t timestamp, bool eligible) {
        update(id, x, y, timestamp, eligible);
        const bool tap = _active;
        cancel();
        return tap;
    }
private:
    bool _active { false };
    int _id { -1 };
    double _x { 0 }, _y { 0 };
    uint64_t _timestamp { 0 };
};
