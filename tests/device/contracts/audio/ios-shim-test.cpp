// SPDX-License-Identifier: Apache-2.0
#include "../../../../libraries/audio-client/src/IOSAudioPermission.h"
#include <cassert>
#include <iostream>
#include <atomic>
#include <thread>
using namespace overte::audio;
struct TestNative : IOSAudioSessionAdapter {
    AudioLifecycleGate gate;
    int requests {0};
    bool microphonePermissionGranted() override { return gate.outcome()==Outcome::Capturing; }
    void requestMicrophonePermission() override { ++requests; }
    bool activate() override { gate.requestStart(); return gate.mayActivate(); }
    bool deactivate() override { gate.stop(); return true; }
};
int main() {
    int notifications = 0;
    notifyIOSAudioStateChanged();
    setIOSAudioStateCallback([&] { ++notifications; });
    notifyIOSAudioStateChanged();
    assert(notifications == 1);
    std::atomic<int> concurrent {0};
    setIOSAudioStateCallback([&] { ++concurrent; });
    std::thread notifier([] { for (int i=0; i<1000; ++i) { notifyIOSAudioStateChanged(); } });
    setIOSAudioStateCallback({});
    const int afterUnregister = concurrent.load();
    notifier.join();
    assert(concurrent == afterUnregister);
    setIOSAudioStateCallback({});
    notifyIOSAudioStateChanged();
    assert(notifications == 1);
    assert(!overteIOSMicrophonePermissionGranted());
    overteIOSRequestMicrophonePermission();
    assert(!overteIOSActivateAudioSession() && !overteIOSDeactivateAudioSession());
    assert(!installIOSAudioSessionAdapter(nullptr));
    auto native=std::make_shared<TestNative>();
    assert(installIOSAudioSessionAdapter(native));
    assert(!installIOSAudioSessionAdapter(std::make_shared<TestNative>()));
    assert(!overteIOSActivateAudioSession());
    native->gate.foreground(true);
    assert(overteIOSActivateAudioSession());
    overteIOSRequestMicrophonePermission(); assert(native->requests==1);
    native->gate.permission(Permission::Granted);
    assert(overteIOSMicrophonePermissionGranted());
    bool failedStateNotified = false;
    native->gate.fail(); // Native stop attempted but did not complete successfully.
    setIOSAudioStateCallback([&] {
        failedStateNotified = !overteIOSMicrophonePermissionGranted();
    });
    notifyIOSAudioStateChanged();
    assert(failedStateNotified && native->gate.outcome() == Outcome::Failed);
    assert(!native->gate.mayActivate());
    setIOSAudioStateCallback({});
    native->gate.requestStart();
    native->gate.interruption(true); assert(!overteIOSMicrophonePermissionGranted());
    assert(overteIOSDeactivateAudioSession());
    native->gate.interruption(false); assert(!overteIOSMicrophonePermissionGranted());
    std::cout << "SH-006 existing four AudioClient symbols, registration and absent binding PASS\n";
}
