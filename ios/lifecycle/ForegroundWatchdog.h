// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <mutex>
#include <utility>

namespace overte::ios {

// Suspension stops the GUI heartbeat as well as the watchdog thread. Keep
// lifecycle eligibility separate from temporary graphics/system-sleep pauses.
class ForegroundWatchdog {
public:
    class Check {
    public:
        explicit Check(ForegroundWatchdog& owner) : _lock(owner._mutex), _active(owner._active) {}
        bool active() const { return _active; }
    private:
        std::unique_lock<std::mutex> _lock;
        bool _active;
    };

    template<class RefreshHeartbeat>
    void observeActive(bool active, RefreshHeartbeat&& refreshHeartbeat) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (active && !_active) {
            // No watchdog sample may straddle resumption and use an old
            // heartbeat. Refresh while checks are excluded, then re-enable.
            std::forward<RefreshHeartbeat>(refreshHeartbeat)();
        }
        _active = active;
    }

    Check acquireCheck() { return Check(*this); }

private:
    std::mutex _mutex;
    bool _active { false };
};

} // namespace overte::ios
