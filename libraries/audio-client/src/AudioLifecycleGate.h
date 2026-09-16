// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <mutex>

namespace overte { namespace audio {
enum class Permission { Unknown, Granted, Denied, Revoked };
enum class Outcome { Stopped, PlaybackOnly, Capturing, Muted, Suspended, Interrupted, Failed };

// No buffers, routes, IDs or timestamps are retained. Native owners serialize
// actual device operations; this gate determines whether those operations may run.
class AudioLifecycleGate {
public:
    std::uint64_t beginPermissionRequest() {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!_requested || !_foreground || _interrupted) { return 0; }
        _pending = ++_generation;
        return _pending;
    }
    bool completePermission(std::uint64_t ticket, Permission permission) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!ticket || ticket != _pending || !_foreground || !_requested || _interrupted) { return false; }
        _pending = 0;
        _permission = permission;
        return true;
    }
    void requestStart() { std::lock_guard<std::mutex> lock(_mutex); _requested = true; _failed = false; }
    void stop() { std::lock_guard<std::mutex> lock(_mutex); _requested = false; invalidate(); }
    void foreground(bool value) {
        std::lock_guard<std::mutex> lock(_mutex);
        _foreground = value;
        if (!value) { invalidate(); }
    }
    void interruption(bool value) {
        std::lock_guard<std::mutex> lock(_mutex);
        _interrupted = value;
        if (value) { invalidate(); }
    }
    void permission(Permission value) {
        std::lock_guard<std::mutex> lock(_mutex);
        _permission = value;
        invalidate();
    }
    void muted(bool value) { std::lock_guard<std::mutex> lock(_mutex); _muted = value; }
    void fail() { std::lock_guard<std::mutex> lock(_mutex); _failed = true; invalidate(); }
    Outcome outcome() const {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!_requested) { return Outcome::Stopped; }
        if (_failed) { return Outcome::Failed; }
        if (!_foreground) { return Outcome::Suspended; }
        if (_interrupted) { return Outcome::Interrupted; }
        if (_muted) { return Outcome::Muted; }
        return _permission == Permission::Granted ? Outcome::Capturing : Outcome::PlaybackOnly;
    }
    bool mayActivate() const {
        const auto state = outcome();
        return state == Outcome::Capturing || state == Outcome::PlaybackOnly || state == Outcome::Muted;
    }
private:
    void invalidate() { ++_generation; _pending = 0; }
    mutable std::mutex _mutex;
    std::uint64_t _generation { 0 }, _pending { 0 };
    Permission _permission { Permission::Unknown };
    bool _requested { false }, _foreground { false }, _interrupted { false }, _muted { false }, _failed { false };
};
}} // namespace overte::audio
