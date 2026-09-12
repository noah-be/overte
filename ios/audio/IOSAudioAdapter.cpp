// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "IOSAudioAdapter.h"

namespace overte::ios {
bool IOSAudioAdapter::apply(bool notify) {
    const auto revision = ++_revision;
    std::lock_guard<std::recursive_mutex> operationLock(_applyMutex);
    if (_revision != revision) { return false; }
    _playback = false;
    _capture = false;
    const auto failed = [this, notify, revision] {
        if (_revision != revision) { return false; } // superseded operation
        invalidatePermissionRequest();
        _capture = false;
        _gate.fail();
        // v003: Failed is an observation requiring Qt containment, not a
        // successful native-stop receipt. Keep native cleanup pending.
        if (notify) { audio::notifyIOSAudioStateChanged(); }
        return false;
    };
    if (!_native) { return failed(); }
    try {
        if (!_gate.mayActivate()) {
            if (!_native->deactivate()) { return failed(); }
            if (_revision != revision) { return false; }
            if (notify) { audio::notifyIOSAudioStateChanged(); }
            return true;
        }
        const bool capture = _gate.outcome() == audio::Outcome::Capturing;
        std::weak_ptr<IOSAudioAdapter> weak = shared_from_this();
        const bool active = _native->activate(capture, [weak, revision] {
            auto self = weak.lock();
            return self && self->_revision == revision && self->_gate.mayActivate();
        });
        if (!active || _revision != revision || !_gate.mayActivate()) {
            return failed();
        }
        _capture = capture && _gate.outcome() == audio::Outcome::Capturing;
        _playback = true;
        ++_outputRevision;
        if (notify) { audio::notifyIOSAudioStateChanged(); }
        return true;
    } catch (...) {
        return failed();
    }
}

bool IOSAudioAdapter::microphonePermissionGranted() {
    refreshPermission();
    return _capture && _permission == audio::Permission::Granted &&
        _gate.outcome() == audio::Outcome::Capturing;
}

void IOSAudioAdapter::refreshPermission() {
    if (!_native) { _capture = false; return; }
    try {
        const auto permission = _native->permission();
        _permissionQueryFailed = false;
        if (_permission.exchange(permission) != permission) {
            invalidatePermissionRequest();
            _capture = false;
            _gate.permission(permission);
            apply();
        }
    } catch (...) {
        _capture = false;
        // A repeated failing permission query must not enqueue itself forever
        // through Shared's refresh callback. Notify the failure transition once.
        // Gate reports Stopped before Failed when no start is requested, so
        // notification suppression cannot depend on its Outcome alone.
        if (!_permissionQueryFailed.exchange(true)) {
            invalidatePermissionRequest();
            _gate.fail();
            apply(); // attempt bounded native stop before failure notification
        }
    }
}

void IOSAudioAdapter::requestMicrophonePermission() {
    _promptRequested = true;
    promptIfNeeded();
}

void IOSAudioAdapter::promptIfNeeded() {
    if (!_native || !_promptRequested || !_gate.mayActivate()) { return; }
    refreshPermission();
    if (_permission != audio::Permission::Unknown) { _promptRequested = false; return; }
    std::uint64_t ticket, epoch;
    {
        std::lock_guard<std::mutex> lock(_permissionMutex);
        // Keep the slot until the native completion, even after cancellation:
        // an already presented OS permission dialog cannot be dismissed here.
        if (_pendingPermission || !_promptRequested.exchange(false)) { return; }
        ticket = _gate.beginPermissionRequest();
        if (!ticket) { return; }
        _pendingPermission = ticket;
        epoch = _permissionEpoch;
    }
    std::weak_ptr<IOSAudioAdapter> weak = shared_from_this();
    auto completion = [weak, ticket, epoch](audio::Permission permission) {
        auto self = weak.lock();
        if (!self) { return; }
        {
            std::lock_guard<std::mutex> lock(self->_permissionMutex);
            if (self->_pendingPermission != ticket) { return; }
            self->_pendingPermission = 0;
            if (self->_permissionEpoch != epoch ||
                    !self->_gate.completePermission(ticket, permission)) { return; }
            // A native queue cancellation is not a permission observation and
            // must not activate audio while UIKit is becoming inactive.
            if (permission == audio::Permission::Unknown) { return; }
            self->_permission = permission;
        }
        self->apply();
    };
    try {
        _native->requestPermission([weak, ticket, epoch] {
            auto self = weak.lock();
            if (!self) { return false; }
            std::lock_guard<std::mutex> lock(self->_permissionMutex);
            return self->_pendingPermission == ticket && self->_permissionEpoch == epoch &&
                self->_permission == audio::Permission::Unknown && self->_gate.mayActivate();
        }, completion);
    } catch (...) {
        invalidatePermissionRequest();
        completion(audio::Permission::Unknown);
        _gate.fail(); _capture = false; apply();
    }
}

void IOSAudioAdapter::invalidatePermissionRequest() {
    std::lock_guard<std::mutex> lock(_permissionMutex);
    ++_permissionEpoch;
}

bool IOSAudioAdapter::activate() {
    _gate.requestStart();
    const bool allowed = _gate.mayActivate();
    const bool success = apply();
    if (success && allowed) { promptIfNeeded(); }
    return success && allowed;
}
bool IOSAudioAdapter::deactivate() {
    invalidatePermissionRequest();
    _capture = false;
    _promptRequested = false;
    ++_revision;
    // Invalidate pending permission without reporting Stopped before the OS.
    _gate.requestStart();
    _gate.fail();
    const bool success = apply(false);
    if (success) {
        _gate.stop();
    }
    audio::notifyIOSAudioStateChanged(); // Stopped on success, Failed otherwise
    return success;
}
void IOSAudioAdapter::routeChanged() {
    refreshPermission();
    // Route changes do not reconfigure AVAudioSession themselves: that could
    // produce another route notification. Shared reopens its current Qt input.
    if (_gate.outcome() != audio::Outcome::Failed) {
        ++_outputRevision;
        audio::notifyIOSAudioStateChanged();
    }
}
void IOSAudioAdapter::foreground(bool active) {
    if (!active) { invalidatePermissionRequest(); }
    _capture = false;
    _gate.foreground(active);
    if (active) { refreshPermission(); }
    apply();
    if (active) { promptIfNeeded(); }
}
void IOSAudioAdapter::interruption(bool began, bool shouldResume) {
    if (began || !shouldResume) { invalidatePermissionRequest(); }
    _capture = false;
    _gate.interruption(began);
    if (!began && !shouldResume) { _gate.stop(); }
    apply();
}
void IOSAudioAdapter::muted(bool value) {
    _capture = false;
    _gate.muted(value);
    apply();
}
} // namespace overte::ios
