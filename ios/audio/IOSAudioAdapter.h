// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../libraries/audio-client/src/IOSAudioPermission.h"
#include <atomic>
#include <functional>

namespace overte::ios {
// Local native execution seam. Production uses AVAudioSession; tests substitute
// OS calls only and execute this same adapter and the published Shared gate.
class NativeAudioOperations {
public:
    virtual ~NativeAudioOperations() = default;
    virtual bool activate(bool capture, std::function<bool()> stillCurrent) = 0;
    virtual bool deactivate() = 0;
    virtual audio::Permission permission() = 0;
    virtual void requestPermission(std::function<void(audio::Permission)> completion) = 0;
};

class IOSAudioAdapter final : public audio::IOSAudioSessionAdapter,
                              public std::enable_shared_from_this<IOSAudioAdapter> {
public:
    explicit IOSAudioAdapter(std::shared_ptr<NativeAudioOperations> native) : _native(std::move(native)) {}
    bool microphonePermissionGranted() override;
    void requestMicrophonePermission() override;
    bool activate() override;
    bool deactivate() override;
    void foreground(bool active);
    void interruption(bool began, bool shouldResume = false);
    void muted(bool value);
    void refreshPermission();
    void routeChanged();
    audio::Outcome outcome() const { return _gate.outcome(); }
private:
    bool apply(bool notify = true);
    void promptIfNeeded();
    std::shared_ptr<NativeAudioOperations> _native;
    audio::AudioLifecycleGate _gate;
    std::atomic<bool> _capture { false }, _promptRequested { false };
    std::atomic<audio::Permission> _permission { audio::Permission::Unknown };
    std::atomic<std::uint64_t> _revision { 0 };
};
} // namespace overte::ios
