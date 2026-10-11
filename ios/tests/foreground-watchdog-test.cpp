// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../lifecycle/ForegroundWatchdog.h"

#include <cassert>
#include <chrono>
#include <future>

int main() {
    using overte::ios::ForegroundWatchdog;
    ForegroundWatchdog lifecycle;
    unsigned now = 0, heartbeat = 0, refreshes = 0;
    const auto refresh = [&] { heartbeat = now; ++refreshes; };
    const auto timedOut = [&] {
        auto check = lifecycle.acquireCheck();
        return check.active() && now - heartbeat > 120;
    };

    now = 300;
    assert(!timedOut()); // startup may occur while already backgrounded
    lifecycle.observeActive(true, refresh);
    assert(!timedOut() && heartbeat == 300);
    now += 121;
    assert(timedOut()); // real foreground deadlocks are still detected
    lifecycle.observeActive(true, refresh);
    assert(timedOut() && refreshes == 1); // duplicate active cannot mask a hang

    lifecycle.observeActive(false, refresh);
    for (unsigned duration : {30, 150, 600}) {
        now += duration;
        assert(!timedOut());
        // A scoped graphics pause/resume can refresh the heartbeat, but cannot
        // re-enable this independent lifecycle gate during suspension.
        refresh();
        now += 150;
        assert(!timedOut());
        lifecycle.observeActive(true, refresh);
        assert(!timedOut() && heartbeat == now);
        now += 120;
        assert(!timedOut());
        ++now;
        assert(timedOut());
        lifecycle.observeActive(false, refresh);
    }

    // The resume operation cannot publish active between a stale sample and
    // its crash decision. The in-flight check retains the same exclusion lock.
    std::future<void> resumed;
    std::promise<void> entered;
    {
        auto check = lifecycle.acquireCheck();
        assert(!check.active());
        resumed = std::async(std::launch::async, [&] {
            entered.set_value();
            lifecycle.observeActive(true, refresh);
        });
        entered.get_future().wait();
        assert(resumed.wait_for(std::chrono::milliseconds(30)) == std::future_status::timeout);
    }
    resumed.get();
    assert(!timedOut() && heartbeat == now);
}
