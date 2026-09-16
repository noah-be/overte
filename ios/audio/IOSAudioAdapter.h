// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../libraries/audio-client/src/IOSAudioPermission.h"
#include <atomic>
#include <functional>
#include <mutex>

namespace overte::ios {
// Local native execution seam. Production uses AVAudioSession; tests substitute
// OS calls only and execute this same adapter and the published Shared gate.
class NativeAudioOperations {
public:
    virtual ~NativeAudioOperations() = default;
    virtual bool activate(bool capture, std::function<bool()> stillCurrent) = 0;
    virtual bool deactivate() = 0;
    virtual audio::Permission permission() = 0;
    // Recheck on the native presentation queue before asking the OS. A skipped
    // request must still complete (Unknown) to release the single pending slot.
    virtual void requestPermission(std::function<bool()> stillCurrent,
                                   std::function<void(audio::Permission)> completion) = 0;
};

class IOSAudioAdapter final : public audio::IOSAudioSessionAdapter,
                              public std::enable_shared_from_this<IOSAudioAdapter> {
public:
    explicit IOSAudioAdapter(std::shared_ptr<NativeAudioOperations> native) : _native(std::move(native)) {}
    bool microphonePermissionGranted() override;
    void requestMicrophonePermission() override;
    bool activate() override;
    bool deactivate() override;
    bool playbackAllowed() const override { return _playback && _gate.mayActivate(); }
    std::uint64_t outputRevision() const override { return _outputRevision; }
    void foreground(bool active);
    void interruption(bool began, bool shouldResume = false);
    void muted(bool value);
    void refreshPermission();
    void routeChanged();
    audio::Outcome outcome() const { return _gate.outcome(); }
private:
    bool apply(bool notify = true);
    void promptIfNeeded();
    void invalidatePermissionRequest();
    std::shared_ptr<NativeAudioOperations> _native;
    audio::AudioLifecycleGate _gate;
    std::atomic<bool> _playback { false };
    std::atomic<std::uint64_t> _outputRevision { 0 };
    std::atomic<bool> _capture { false }, _promptRequested { false };
    std::atomic<bool> _permissionQueryFailed { false };
    std::atomic<audio::Permission> _permission { audio::Permission::Unknown };
    std::atomic<std::uint64_t> _revision { 0 };
    // Serialize native operations, but invalidate an in-flight operation before
    // waiting for it. Concurrent foreground/permission changes must not turn a
    // merely busy executor into a permanent Failed state.
    std::recursive_mutex _applyMutex;
    std::mutex _permissionMutex;
    std::uint64_t _pendingPermission { 0 }, _permissionEpoch { 0 };
};
} // namespace overte::ios
