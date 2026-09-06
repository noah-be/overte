// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <memory>
#include "AudioLifecycleGate.h"

namespace overte { namespace audio {
// Native implementation lives in ios/audio, owns AVAudioSession and dispatches
// its operations on the native serial executor. Gate actual capture/resume with
// AudioLifecycleGate; do not activate after stop, suspension or stale callback.
class IOSAudioSessionAdapter {
public:
    virtual ~IOSAudioSessionAdapter() = default;
    virtual bool microphonePermissionGranted() = 0;
    virtual void requestMicrophonePermission() = 0;
    virtual bool activate() = 0;
    virtual bool deactivate() = 0;
};
bool installIOSAudioSessionAdapter(std::shared_ptr<IOSAudioSessionAdapter> adapter);
}}

// Preserve the exact four existing AudioClient call sites and linked symbols.
bool overteIOSMicrophonePermissionGranted();
void overteIOSRequestMicrophonePermission();
bool overteIOSActivateAudioSession();
bool overteIOSDeactivateAudioSession();
