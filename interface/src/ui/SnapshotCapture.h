// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QString>
#include <atomic>
#include <memory>

// Shared by render callbacks and encoding workers. A cancelled request cannot
// publish a later success, even when the renderer already dequeued its operator.
struct SnapshotCaptureRequest {
    explicit SnapshotCaptureRequest(QString value = {}) : id(std::move(value)) {}
    const QString id;
    enum class State { Active, Cancelled, Completed };
    std::atomic<State> state { State::Active };
    std::atomic<bool> announced { false };
    bool current() const { return state.load() == State::Active; }
    bool cancel() { auto expected = State::Active; return state.compare_exchange_strong(expected, State::Cancelled); }
    bool finish() { auto expected = State::Active; return state.compare_exchange_strong(expected, State::Completed); }
};
using SnapshotCapture = std::shared_ptr<SnapshotCaptureRequest>;
