// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <atomic>
#include <memory>

namespace overte::ios {
// Owner starts/cancels on its serial queue. Tokens may be checked from any queue
// and outlive the owner. Cancellation also invalidates callbacks already queued.
class CallbackEpoch final {
public:
    class Token {
    public:
        bool current() const noexcept { return _active && _active->load(); }
    private:
        friend class CallbackEpoch;
        explicit Token(std::shared_ptr<std::atomic<bool>> active) : _active(std::move(active)) {}
        std::shared_ptr<std::atomic<bool>> _active;
    };
    CallbackEpoch() = default;
    CallbackEpoch(const CallbackEpoch&) = delete;
    CallbackEpoch& operator=(const CallbackEpoch&) = delete;
    ~CallbackEpoch() { cancel(); }
    Token begin() {
        cancel();
        _active = std::make_shared<std::atomic<bool>>(true);
        return Token(_active);
    }
    void cancel() noexcept {
        if (_active) { _active->store(false); }
    }
private:
    std::shared_ptr<std::atomic<bool>> _active;
};
} // namespace overte::ios
