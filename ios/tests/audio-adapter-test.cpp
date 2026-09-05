// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../audio/IOSAudioAdapter.h"
#include <cassert>
#include <stdexcept>
using namespace overte::ios;
using namespace overte::audio;
struct Native final : NativeAudioOperations {
    Permission granted { Permission::Unknown };
    bool failStart { false }, failStop { false }, captures { false };
    bool throwPermission { false };
    int starts { 0 }, stops { 0 };
    std::function<void(Permission)> completion;
    std::function<bool()> lastValidity;
    bool activate(bool capture, std::function<bool()> current) override {
        ++starts; lastValidity = current;
        captures = !failStart && capture && current();
        return !failStart && current();
    }
    bool deactivate() override { ++stops; if (!failStop) { captures = false; } return !failStop; }
    Permission permission() override {
        if (throwPermission) { throw std::runtime_error("synthetic permission fault"); }
        return granted;
    }
    void requestPermission(std::function<void(Permission)> callback) override { completion = callback; }
};
int main() {
    auto native = std::make_shared<Native>();
    auto adapter = std::make_shared<IOSAudioAdapter>(native);
    int notifications = 0;
    Outcome notified = Outcome::Stopped;
    bool observedPendingNativeStop = false;
    setIOSAudioStateCallback([&] {
        ++notifications;
        notified = adapter->outcome();
        // Real Shared callback only enqueues. Check native state here without
        // reentering the registry or querying native permission.
        if (notified == Outcome::Failed) {
            observedPendingNativeStop |= native->captures;
        } else {
            assert(native->captures == (notified == Outcome::Capturing));
        }
    });
    assert(!adapter->activate() && native->starts == 0);
    adapter->foreground(true);
    assert(adapter->activate() && !adapter->microphonePermissionGranted());
    adapter->requestMicrophonePermission();
    assert(native->completion);
    auto stale = native->completion;
    assert(adapter->deactivate());
    assert(notified == Outcome::Stopped);
    const auto stoppedNotifications = notifications;
    stale(Permission::Granted);
    assert(notifications == stoppedNotifications);
    assert(adapter->outcome() == Outcome::Stopped && !adapter->microphonePermissionGranted());
    assert(adapter->activate()); // stop did not invent a background transition
    adapter->requestMicrophonePermission();
    native->granted = Permission::Granted;
    native->completion(Permission::Granted);
    assert(notified == Outcome::Capturing);
    assert(adapter->microphonePermissionGranted() && native->captures);
    adapter->muted(true);
    assert(!adapter->microphonePermissionGranted() && !native->captures);
    adapter->muted(false);
    assert(adapter->microphonePermissionGranted());
    auto priorActivation = native->lastValidity;
    adapter->foreground(false);
    assert(notified == Outcome::Suspended);
    assert(!priorActivation() && !adapter->microphonePermissionGranted() && !native->captures);
    adapter->foreground(true);
    adapter->interruption(true);
    assert(!adapter->microphonePermissionGranted());
    adapter->interruption(false, false);
    assert(adapter->outcome() == Outcome::Stopped && !native->captures);
    assert(adapter->activate());
    native->granted = Permission::Denied;
    assert(!adapter->microphonePermissionGranted() && !native->captures);
    native->granted = Permission::Granted;
    adapter->refreshPermission();
    assert(native->captures);
    native->failStop = true;
    const auto beforeFailedStop = notifications;
    assert(!adapter->deactivate() && adapter->outcome() == Outcome::Failed);
    assert(notifications == beforeFailedStop + 1 && notified == Outcome::Failed);
    assert(observedPendingNativeStop && !adapter->microphonePermissionGranted());
    for (int i = 0; i < 100; ++i) { assert(!adapter->microphonePermissionGranted()); }
    assert(notifications == beforeFailedStop + 1); // no refresh feedback loop
    native->failStop = false;
    assert(adapter->deactivate() && adapter->outcome() == Outcome::Stopped);
    native->failStart = true;
    assert(!adapter->activate() && !adapter->microphonePermissionGranted());
    assert(adapter->outcome() == Outcome::Failed);
    native->failStart = false;
    assert(adapter->activate());
    native->throwPermission = true;
    const auto beforePermissionFailure = notifications;
    assert(!adapter->microphonePermissionGranted() && !native->captures);
    assert(notifications == beforePermissionFailure + 1 && notified == Outcome::Failed);
    for (int i = 0; i < 100; ++i) { assert(!adapter->microphonePermissionGranted()); }
    assert(notifications == beforePermissionFailure + 1);
    native->throwPermission = false;
    assert(adapter->activate()); // only explicit restart leaves Failed
    const auto beforeRoute = notifications;
    const auto beforeRouteStarts = native->starts;
    adapter->routeChanged();
    assert(notifications == beforeRoute + 1 && native->starts == beforeRouteStarts);
    setIOSAudioStateCallback({});
    adapter->routeChanged();
    assert(notifications == beforeRoute + 1);
}
