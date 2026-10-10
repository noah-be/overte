// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <memory>
#include "AudioLifecycleGate.h"

namespace overte { namespace audio {
#if defined(OVERTE_E2E_VOICE_TESTS)
struct IOSVoiceTestState {
    Permission permission { Permission::Unknown };
    Outcome outcome { Outcome::Stopped };
    bool foreground { false }, interrupted { false }, captureAllowed { false };
};
#endif
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
    // Legacy adapters stop conservatively; native implementations retain mute state.
    virtual void muted(bool value) { if (value) { deactivate(); } }
#if defined(OVERTE_E2E_VOICE_TESTS)
    // Closed observations only; no device identifiers, routes or native messages.
    virtual IOSVoiceTestState voiceTestState() const { return {}; }
#endif
};
bool installIOSAudioSessionAdapter(std::shared_ptr<IOSAudioSessionAdapter> adapter);
}}

// Preserve the exact four existing AudioClient call sites and linked symbols.
bool overteIOSMicrophonePermissionGranted();
void overteIOSRequestMicrophonePermission();
bool overteIOSActivateAudioSession();
bool overteIOSDeactivateAudioSession();

void overteIOSSetAudioMuted(bool muted);
#if defined(OVERTE_E2E_VOICE_TESTS)
overte::audio::IOSVoiceTestState overteIOSVoiceTestState();
#endif
