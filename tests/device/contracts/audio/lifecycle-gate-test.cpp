// SPDX-License-Identifier: Apache-2.0
#include "../../../../libraries/audio-client/src/AudioLifecycleGate.h"
#include <cassert>
#include <iostream>
using namespace overte::audio;
int main() {
    AudioLifecycleGate gate;
    assert(gate.outcome()==Outcome::Stopped && !gate.mayActivate());
    assert(gate.beginPermissionRequest()==0);
    gate.requestStart(); assert(gate.outcome()==Outcome::Suspended);
    gate.foreground(true); assert(gate.outcome()==Outcome::PlaybackOnly && gate.mayActivate());
    auto stale=gate.beginPermissionRequest(); auto current=gate.beginPermissionRequest();
    assert(!gate.completePermission(stale,Permission::Granted));
    assert(gate.completePermission(current,Permission::Denied));
    assert(!gate.completePermission(current,Permission::Granted));
    assert(gate.outcome()==Outcome::PlaybackOnly);
    current=gate.beginPermissionRequest(); gate.foreground(false);
    assert(!gate.completePermission(current,Permission::Granted) && !gate.mayActivate());
    gate.foreground(true); current=gate.beginPermissionRequest();
    assert(gate.completePermission(current,Permission::Granted));
    assert(gate.outcome()==Outcome::Capturing);
    gate.muted(true); assert(gate.outcome()==Outcome::Muted);
    gate.permission(Permission::Revoked); gate.muted(false);
    assert(gate.outcome()==Outcome::PlaybackOnly);
    current=gate.beginPermissionRequest(); gate.interruption(true);
    assert(!gate.completePermission(current,Permission::Granted));
    assert(gate.outcome()==Outcome::Interrupted && !gate.mayActivate());
    gate.foreground(false); gate.interruption(false);
    assert(!gate.mayActivate());
    gate.foreground(true); current=gate.beginPermissionRequest(); gate.stop();
    assert(!gate.completePermission(current,Permission::Granted));
    assert(gate.outcome()==Outcome::Stopped);
    gate.requestStart(); gate.fail(); assert(gate.outcome()==Outcome::Failed && !gate.mayActivate());
    gate.stop(); assert(gate.outcome()==Outcome::Stopped);
    std::cout << "SH-006 permission generation, revoke, mute, interruption, suspend and stop PASS\n";
}
