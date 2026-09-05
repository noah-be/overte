// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "IOSAudioAdapter.h"

namespace overte::ios {
bool IOSAudioAdapter::apply() {
    const auto revision = ++_revision;
    _capture = false;
    if (!_native) { _gate.fail(); return false; }
    try {
        if (!_gate.mayActivate()) {
            if (!_native->deactivate()) { _gate.fail(); return false; }
            return true;
        }
        const bool capture = _gate.outcome() == audio::Outcome::Capturing;
        std::weak_ptr<IOSAudioAdapter> weak = shared_from_this();
        const bool active = _native->activate(capture, [weak, revision] {
            auto self = weak.lock();
            return self && self->_revision == revision && self->_gate.mayActivate();
        });
        if (!active || _revision != revision || !_gate.mayActivate()) {
            _gate.fail();
            return false;
        }
        _capture = capture && _gate.outcome() == audio::Outcome::Capturing;
        return true;
    } catch (...) {
        _gate.fail();
        return false;
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
        if (_permission.exchange(permission) != permission) {
            _capture = false;
            _gate.permission(permission);
            apply();
        }
    } catch (...) { _capture = false; _gate.fail(); }
}

void IOSAudioAdapter::requestMicrophonePermission() {
    _promptRequested = true;
    promptIfNeeded();
}

void IOSAudioAdapter::promptIfNeeded() {
    if (!_native || !_promptRequested || !_gate.mayActivate()) { return; }
    refreshPermission();
    if (_permission != audio::Permission::Unknown) { _promptRequested = false; return; }
    const auto ticket = _gate.beginPermissionRequest();
    if (!ticket || !_promptRequested.exchange(false)) { return; }
    std::weak_ptr<IOSAudioAdapter> weak = shared_from_this();
    try {
        _native->requestPermission([weak, ticket](audio::Permission permission) {
            auto self = weak.lock();
            if (!self || !self->_gate.completePermission(ticket, permission)) { return; }
            self->_permission = permission;
            self->apply();
        });
    } catch (...) { _gate.fail(); _capture = false; }
}

bool IOSAudioAdapter::activate() {
    _gate.requestStart();
    const bool allowed = _gate.mayActivate();
    const bool success = apply();
    if (success && allowed) { promptIfNeeded(); }
    return success && allowed;
}
bool IOSAudioAdapter::deactivate() {
    _capture = false;
    _promptRequested = false;
    ++_revision;
    // Invalidate pending permission without reporting Stopped before the OS.
    _gate.requestStart();
    _gate.fail();
    const bool success = apply();
    if (success) { _gate.stop(); }
    return success;
}
void IOSAudioAdapter::foreground(bool active) {
    _capture = false;
    _gate.foreground(active);
    if (active) { refreshPermission(); }
    apply();
    if (active) { promptIfNeeded(); }
}
void IOSAudioAdapter::interruption(bool began, bool shouldResume) {
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
