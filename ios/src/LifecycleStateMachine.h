// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstdint>
#include <mutex>

namespace overte::ios {

enum class LifecycleState {
    Cold,
    Inactive,
    Active,
    Background,
    Terminating,
};

enum class LifecycleEvent {
    DidFinishLaunching,
    DidBecomeActive,
    WillResignActive,
    DidEnterBackground,
    WillEnterForeground,
    DidReceiveMemoryWarning,
    WillTerminate,
};

struct LifecycleSnapshot {
    LifecycleState state { LifecycleState::Cold };
    std::uint64_t transitionSequence { 0 };
    std::uint64_t memoryWarnings { 0 };
};

class LifecycleStateMachine {
public:
    static LifecycleStateMachine& instance();

    bool apply(LifecycleEvent event);
    LifecycleSnapshot snapshot() const;

private:
    mutable std::mutex _mutex;
    LifecycleSnapshot _snapshot;
};

} // namespace overte::ios
