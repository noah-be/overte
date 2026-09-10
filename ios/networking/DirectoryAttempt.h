// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../interface/src/ApplicationLifecycle.h"

namespace overte::ios {
// Native preview directory attempts, NOT the full-client connection instance.
// Reuse the original Shared engine; no URL enters its exportable state.
class DirectoryAttempt {
public:
    void visible(bool value) { _gate.visible(value); }
    std::uint64_t begin(std::uint64_t now) {
        if (_intent == UINT64_MAX) { _gate.stop(); return 0; }
        const auto transition = _gate.begin(++_intent, now);
        return transition.accepted ? transition.snapshot.generation : 0;
    }
    std::uint64_t retry(std::uint64_t now) {
        const auto transition = _gate.retry(_gate.snapshot().generation, now);
        return transition.accepted ? transition.snapshot.generation : 0;
    }
    bool complete(std::uint64_t ticket, std::uint64_t now) {
        if (_gate.connected(ticket, now).accepted) { return true; }
        _gate.timeout(ticket, now);
        return false;
    }
    void failed(std::uint64_t ticket) { _gate.lost(ticket); }
    void cancel() { _gate.lost(_gate.snapshot().generation); }
    void stop() { _gate.stop(); }
    lifecycle::Snapshot snapshot() const { return _gate.snapshot(); }
private:
    lifecycle::Gate _gate;
    std::uint64_t _intent { 0 };
};
}
