// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../audio/IOSAudioAdapter.h"
#include <cassert>
using namespace overte::ios;
using namespace overte::audio;
struct Native final : NativeAudioOperations {
    Permission granted { Permission::Unknown };
    bool failStart { false }, failStop { false }, captures { false };
    int starts { 0 }, stops { 0 };
    std::function<void(Permission)> completion;
    std::function<bool()> lastValidity;
    bool activate(bool capture, std::function<bool()> current) override {
        ++starts; lastValidity = current;
        captures = !failStart && capture && current();
        return !failStart && current();
    }
    bool deactivate() override { ++stops; captures = false; return !failStop; }
    Permission permission() override { return granted; }
    void requestPermission(std::function<void(Permission)> callback) override { completion = callback; }
};
int main() {
    auto native = std::make_shared<Native>();
    auto adapter = std::make_shared<IOSAudioAdapter>(native);
    assert(!adapter->activate() && native->starts == 0);
    adapter->foreground(true);
    assert(adapter->activate() && !adapter->microphonePermissionGranted());
    adapter->requestMicrophonePermission();
    assert(native->completion);
    auto stale = native->completion;
    assert(adapter->deactivate());
    stale(Permission::Granted);
    assert(adapter->outcome() == Outcome::Stopped && !adapter->microphonePermissionGranted());
    assert(adapter->activate()); // stop did not invent a background transition
    adapter->requestMicrophonePermission();
    native->granted = Permission::Granted;
    native->completion(Permission::Granted);
    assert(adapter->microphonePermissionGranted() && native->captures);
    adapter->muted(true);
    assert(!adapter->microphonePermissionGranted() && !native->captures);
    adapter->muted(false);
    assert(adapter->microphonePermissionGranted());
    auto priorActivation = native->lastValidity;
    adapter->foreground(false);
    assert(!priorActivation() && !adapter->microphonePermissionGranted() && !native->captures);
    adapter->foreground(true);
    adapter->interruption(true);
    assert(!adapter->microphonePermissionGranted());
    adapter->interruption(false, false);
    assert(adapter->outcome() == Outcome::Stopped && !native->captures);
    assert(adapter->activate());
    native->granted = Permission::Denied;
    assert(!adapter->microphonePermissionGranted() && !native->captures);
    native->failStop = true;
    assert(!adapter->deactivate() && adapter->outcome() == Outcome::Failed);
    native->failStop = false;
    assert(adapter->deactivate() && adapter->outcome() == Outcome::Stopped);
    native->failStart = true;
    assert(!adapter->activate() && !adapter->microphonePermissionGranted());
    assert(adapter->outcome() == Outcome::Failed);
}
