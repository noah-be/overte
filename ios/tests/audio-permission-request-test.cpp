// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../audio/IOSAudioAdapter.h"
#include <cassert>
#include <stdexcept>
using namespace overte::ios;
using namespace overte::audio;

struct QueuedNative final : NativeAudioOperations {
    Permission observed { Permission::Unknown };
    int requests { 0 }, prompts { 0 }, starts { 0 };
    bool throws { false };
    std::function<bool()> current;
    std::function<void(Permission)> completion;
    bool activate(bool, std::function<bool()> valid) override { ++starts; return valid(); }
    bool deactivate() override { return true; }
    Permission permission() override { return observed; }
    // The old overload permits the same regression to execute against baseline.
    void requestPermission(std::function<void(Permission)> done) {
        requestPermission([] { return true; }, done);
    }
    void requestPermission(std::function<bool()> valid, std::function<void(Permission)> done) {
        ++requests;
        if (throws) { throw std::runtime_error("synthetic scheduling failure"); }
        current = valid; completion = done;
    }
    void drain() {
        if (current()) { ++prompts; }
        else { completion(Permission::Unknown); }
    }
};

int main() {
    // Pause the native presentation queue, invalidate, then drain it. Even an
    // intervening restart/resume must not resurrect the old user prompt.
    for (int event = 0; event < 4; ++event) {
        auto native = std::make_shared<QueuedNative>();
        auto adapter = std::make_shared<IOSAudioAdapter>(native);
        adapter->foreground(true); assert(adapter->activate());
        adapter->requestMicrophonePermission();
        assert(native->requests == 1 && native->current());
        if (event == 0) { assert(adapter->deactivate()); assert(adapter->activate()); }
        if (event == 1) { adapter->foreground(false); adapter->foreground(true); }
        if (event == 2) { adapter->interruption(true); adapter->interruption(false, true); }
        if (event == 3) {
            native->observed = Permission::Denied; adapter->refreshPermission();
            native->observed = Permission::Unknown; adapter->refreshPermission();
        }
        const auto starts = native->starts;
        native->drain();
        assert(native->prompts == 0 && native->starts == starts);
        adapter->requestMicrophonePermission();
        assert(native->requests == 2 && native->current());
        native->drain(); assert(native->prompts == 1);
        native->observed = Permission::Granted;
        native->completion(Permission::Granted);
        assert(adapter->microphonePermissionGranted());
    }
    auto native = std::make_shared<QueuedNative>();
    auto adapter = std::make_shared<IOSAudioAdapter>(native);
    adapter->foreground(true); assert(adapter->activate());
    adapter->requestMicrophonePermission();
    for (int i = 0; i < 100; ++i) { adapter->requestMicrophonePermission(); }
    assert(native->requests == 1);
    native->drain(); assert(native->prompts == 1);
    auto oldCompletion = native->completion;
    adapter->foreground(false); adapter->foreground(true);
    adapter->requestMicrophonePermission();
    assert(native->requests == 1); // already shown dialog still owns the slot
    oldCompletion(Permission::Granted); // stale grant releases only its own slot
    assert(!adapter->microphonePermissionGranted());
    adapter->requestMicrophonePermission();
    assert(native->requests == 2 && native->current());
    oldCompletion(Permission::Granted); // duplicate cannot release newer request
    adapter->requestMicrophonePermission();
    assert(native->requests == 2 && native->current());
    native->observed = Permission::Denied;
    native->completion(Permission::Denied);
    assert(!adapter->microphonePermissionGranted() && adapter->outcome() == Outcome::PlaybackOnly);

    native->observed = Permission::Unknown; adapter->refreshPermission();
    adapter->requestMicrophonePermission();
    const auto beforeSkipped = native->starts;
    native->completion(Permission::Unknown); // UIKit inactive before Qt notification
    assert(native->starts == beforeSkipped);
    native->throws = true; adapter->requestMicrophonePermission();
    assert(adapter->outcome() == Outcome::Failed);
    native->throws = false; assert(adapter->activate());
    adapter->requestMicrophonePermission();
    assert(native->current()); // thrown scheduler did not strand the slot
    adapter.reset();
    assert(!native->current());
    native->drain(); // late cancelled completion after owner destruction is safe
}
