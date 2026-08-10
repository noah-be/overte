// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "LifecycleStateMachine.h"

#include <cassert>

using overte::ios::LifecycleEvent;
using overte::ios::LifecycleState;
using overte::ios::LifecycleStateMachine;

int main() {
    LifecycleStateMachine machine;
    assert(machine.snapshot().state == LifecycleState::Cold);
    assert(!machine.apply(LifecycleEvent::DidBecomeActive));
    assert(machine.apply(LifecycleEvent::DidFinishLaunching));
    assert(machine.snapshot().state == LifecycleState::Inactive);
    assert(machine.apply(LifecycleEvent::DidBecomeActive));

    for (int cycle = 0; cycle < 10; ++cycle) {
        assert(machine.apply(LifecycleEvent::WillResignActive));
        assert(machine.apply(LifecycleEvent::DidEnterBackground));
        assert(machine.snapshot().state == LifecycleState::Background);
        assert(machine.apply(LifecycleEvent::DidReceiveMemoryWarning));
        assert(machine.apply(LifecycleEvent::WillEnterForeground));
        assert(machine.apply(LifecycleEvent::DidBecomeActive));
    }
    auto active = machine.snapshot();
    assert(active.state == LifecycleState::Active);
    assert(active.memoryWarnings == 10);
    assert(active.transitionSequence == 52);
    assert(!machine.apply(LifecycleEvent::DidBecomeActive));
    assert(machine.apply(LifecycleEvent::WillTerminate));
    assert(machine.snapshot().state == LifecycleState::Terminating);
    assert(!machine.apply(LifecycleEvent::DidReceiveMemoryWarning));
    return 0;
}
