// SPDX-License-Identifier: Apache-2.0
#include "../../../../libraries/audio-client/src/IOSAudioPermission.h"
#include <cassert>
#include <iostream>
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
    native->gate.interruption(true); assert(!overteIOSMicrophonePermissionGranted());
    assert(overteIOSDeactivateAudioSession());
    native->gate.interruption(false); assert(!overteIOSMicrophonePermissionGranted());
    std::cout << "SH-006 existing four AudioClient symbols, registration and absent binding PASS\n";
}
