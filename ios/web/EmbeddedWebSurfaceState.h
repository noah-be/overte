// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cstdint>
#include <limits>

namespace overte::ios {
// UIKit-thread state for asynchronous WKWebView snapshot delivery. This does
// not grant navigation, JavaScript or credentials; the shared web owner grants
// those separately. Native callbacks must carry the generation they started in.
class EmbeddedWebSurfaceState {
public:
    struct Size { unsigned width { 0 }, height { 0 }; };
    static constexpr unsigned MAX_EDGE = 2048;
    static constexpr std::uint64_t FRAME_INTERVAL_MS = 100;
    static constexpr std::uint64_t SNAPSHOT_TIMEOUT_MS = 2000;

    std::uint64_t reset(Size size, bool foreground) {
        invalidate();
        if (!_generation || !validSize(size) || !foreground) { return 0; }
        _size = size;
        _active = true;
        return _generation;
    }

    void invalidate() {
        // Exhaustion fails closed; never reuse an old callback identity.
        if (_generation == std::numeric_limits<std::uint64_t>::max()) {
            _generation = 0;
            _exhausted = true;
        } else if (!_exhausted) {
            ++_generation;
        }
        _active = false;
        _pending = false;
        _scheduled = false;
        _size = {};
    }

    bool current(std::uint64_t generation) const {
        return _active && generation && generation == _generation;
    }

    bool beginSnapshot(std::uint64_t generation, std::uint64_t nowMs) {
        if (!current(generation) || _pending ||
                (_scheduled && (nowMs < _startedMs || nowMs - _startedMs < FRAME_INTERVAL_MS))) {
            return false;
        }
        _pending = true;
        _scheduled = true;
        _startedMs = nowMs;
        return true;
    }

    bool finishSnapshot(std::uint64_t generation, Size pixels, std::uint64_t nowMs) {
        if (!current(generation) || !_pending) { return false; }
        _pending = false;
        // Native image conversion must use the requested logical size, without
        // unbounded device-scale expansion. A late callback cannot display.
        return pixels.width == _size.width && pixels.height == _size.height &&
            nowMs >= _startedMs && nowMs - _startedMs <= SNAPSHOT_TIMEOUT_MS;
    }

    bool snapshotTimedOut(std::uint64_t generation, std::uint64_t nowMs) const {
        return current(generation) && _pending && nowMs >= _startedMs &&
            nowMs - _startedMs > SNAPSHOT_TIMEOUT_MS;
    }

    Size size() const { return _size; }
    static bool validSize(Size size) {
        return size.width && size.height && size.width <= MAX_EDGE && size.height <= MAX_EDGE;
    }

private:
    std::uint64_t _generation { 0 }, _startedMs { 0 };
    Size _size;
    bool _active { false }, _pending { false }, _scheduled { false }, _exhausted { false };
};
} // namespace overte::ios
