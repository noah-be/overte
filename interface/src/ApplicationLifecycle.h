// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <limits>
#include <mutex>

namespace overte { namespace lifecycle {
enum class State { Suspended, Idle, Connecting, Connected, Recovery, Failed, Stopped };
enum class Action { None, Connect, Retry, Cancel, ShowRecovery };
struct Snapshot {
    State state;
    std::uint64_t generation;
    unsigned attempts;
    bool foreground;
};
struct Transition { bool accepted; Action action; Snapshot snapshot; };

// No URL, user, device, or session identifiers enter this exportable state.
// A ticket belongs to one asynchronous attempt, not just a target or session.
class Gate {
public:
    static constexpr unsigned MAX_ATTEMPTS = 3;
    static constexpr std::uint64_t ATTEMPT_TIMEOUT_MS = 15000;

    Snapshot snapshot() const { std::lock_guard<std::mutex> lock(_mutex); return read(); }

    Transition visible(bool foreground) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_state == State::Stopped || foreground == _foreground) { return result(false, Action::None); }
        _foreground = foreground;
        next();
        if (_state == State::Stopped) { return result(true, Action::Cancel); }
        _state = foreground ? State::Idle : State::Suspended;
        _attempts = 0;
        _request = 0;
        return result(true, foreground ? Action::None : Action::Cancel);
    }

    // request is an in-process opaque sequence assigned to a canonical URL by
    // the caller; it must never be a persisted/hashed endpoint in exported logs.
    Transition begin(std::uint64_t request, std::uint64_t now) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!_foreground || _state == State::Stopped || request == 0 ||
            _request == request) {
            return result(false, Action::None);
        }
        if (!deadline(now)) { return result(false, Action::ShowRecovery); }
        next();
        if (_state == State::Stopped) { return result(false, Action::Cancel); }
        _request = request;
        _attempts = 1;
        _state = State::Connecting;
        return result(true, Action::Connect);
    }

    Transition connected(std::uint64_t ticket, std::uint64_t now) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!current(ticket) || now < _started || now >= _deadline) { return result(false, Action::None); }
        _state = State::Connected;
        return result(true, Action::None);
    }

    Transition lost(std::uint64_t ticket) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!_foreground || ticket != _generation || (_state != State::Connecting && _state != State::Connected)) {
            return result(false, Action::None);
        }
        next(); // Invalidate callbacks before exposing a recoverable state.
        if (_state != State::Stopped) { _state = _attempts < MAX_ATTEMPTS ? State::Recovery : State::Failed; }
        return result(true, Action::ShowRecovery);
    }

    Transition timeout(std::uint64_t ticket, std::uint64_t now) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!current(ticket) || now < _deadline) { return result(false, Action::None); }
        next();
        if (_state != State::Stopped) { _state = _attempts < MAX_ATTEMPTS ? State::Recovery : State::Failed; }
        return result(true, Action::ShowRecovery);
    }

    Transition retry(std::uint64_t recoveryTicket, std::uint64_t now) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (!_foreground || _state != State::Recovery || recoveryTicket != _generation ||
            _attempts >= MAX_ATTEMPTS || !deadline(now)) { return result(false, Action::None); }
        next();
        if (_state == State::Stopped) { return result(false, Action::Cancel); }
        ++_attempts;
        _state = State::Connecting;
        return result(true, Action::Retry);
    }

    Transition stop() {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_state == State::Stopped) { return result(false, Action::None); }
        next();
        _state = State::Stopped;
        _foreground = false;
        _request = 0;
        return result(true, Action::Cancel);
    }

private:
    Snapshot read() const { return { _state, _generation, _attempts, _foreground }; }
    Transition result(bool accepted, Action action) const { return { accepted, action, read() }; }
    bool current(std::uint64_t ticket) const {
        return _foreground && _state == State::Connecting && ticket == _generation;
    }
    void next() {
        if (_generation == std::numeric_limits<std::uint64_t>::max()) { _state = State::Stopped; }
        else { ++_generation; }
    }
    bool deadline(std::uint64_t now) {
        if (now < _lastClock || now > std::numeric_limits<std::uint64_t>::max() - ATTEMPT_TIMEOUT_MS) { return false; }
        _started = _lastClock = now;
        _deadline = now + ATTEMPT_TIMEOUT_MS;
        return true;
    }
    mutable std::mutex _mutex;
    State _state { State::Suspended };
    std::uint64_t _generation { 1 }, _request { 0 }, _started { 0 }, _deadline { 0 }, _lastClock { 0 };
    unsigned _attempts { 0 };
    bool _foreground { false };
};

// One full-client instance, defined out of line to avoid per-DSO singleton copies.
Gate& applicationGate();
} }
