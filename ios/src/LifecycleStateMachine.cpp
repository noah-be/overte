// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "LifecycleStateMachine.h"

namespace overte::ios {

LifecycleStateMachine& LifecycleStateMachine::instance() {
    static LifecycleStateMachine machine;
    return machine;
}

bool LifecycleStateMachine::apply(LifecycleEvent event) {
    std::lock_guard guard(_mutex);
    LifecycleState next = _snapshot.state;
    switch (event) {
        case LifecycleEvent::DidFinishLaunching:
            if (_snapshot.state != LifecycleState::Cold) {
                return false;
            }
            next = LifecycleState::Inactive;
            break;
        case LifecycleEvent::DidBecomeActive:
            if (_snapshot.state != LifecycleState::Inactive) {
                return false;
            }
            next = LifecycleState::Active;
            break;
        case LifecycleEvent::WillResignActive:
            if (_snapshot.state != LifecycleState::Active) {
                return false;
            }
            next = LifecycleState::Inactive;
            break;
        case LifecycleEvent::DidEnterBackground:
            if (_snapshot.state != LifecycleState::Inactive) {
                return false;
            }
            next = LifecycleState::Background;
            break;
        case LifecycleEvent::WillEnterForeground:
            if (_snapshot.state != LifecycleState::Background) {
                return false;
            }
            next = LifecycleState::Inactive;
            break;
        case LifecycleEvent::DidReceiveMemoryWarning:
            if (_snapshot.state == LifecycleState::Cold ||
                    _snapshot.state == LifecycleState::Terminating) {
                return false;
            }
            ++_snapshot.memoryWarnings;
            ++_snapshot.transitionSequence;
            return true;
        case LifecycleEvent::WillTerminate:
            if (_snapshot.state == LifecycleState::Cold ||
                    _snapshot.state == LifecycleState::Terminating) {
                return false;
            }
            next = LifecycleState::Terminating;
            break;
    }
    _snapshot.state = next;
    ++_snapshot.transitionSequence;
    return true;
}

LifecycleSnapshot LifecycleStateMachine::snapshot() const {
    std::lock_guard guard(_mutex);
    return _snapshot;
}

} // namespace overte::ios
