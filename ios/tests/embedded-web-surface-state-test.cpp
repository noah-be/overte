// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../web/EmbeddedWebSurfaceState.h"
#include <cassert>

int main() {
    using State = overte::ios::EmbeddedWebSurfaceState;
    State state;
    assert(!state.reset({ 0, 10 }, true));
    assert(!state.reset({ 2049, 10 }, true));
    assert(!state.reset({ 10, 2049 }, true));
    assert(!state.reset({ 10, 10 }, false));

    const auto first = state.reset({ 640, 480 }, true);
    assert(first);
    assert(state.beginSnapshot(first, 0));
    assert(!state.beginSnapshot(first, 100)); // One native operation in flight.
    assert(state.finishSnapshot(first, { 640, 480 }, 1));
    assert(!state.finishSnapshot(first, { 640, 480 }, 2)); // Duplicate completion.
    assert(!state.beginSnapshot(first, 99));
    assert(state.beginSnapshot(first, 100));

    const auto resized = state.reset({ 800, 600 }, true);
    assert(resized != first);
    assert(state.beginSnapshot(resized, 101));
    assert(!state.finishSnapshot(first, { 640, 480 }, 102));
    assert(!state.beginSnapshot(resized, 201)); // Old callback did not release new operation.
    assert(!state.finishSnapshot(resized, { 1600, 1200 }, 102)); // Reject device-scale expansion.
    assert(state.beginSnapshot(resized, 201));
    assert(!state.snapshotTimedOut(resized, 2201));
    assert(state.snapshotTimedOut(resized, 2202));
    assert(!state.finishSnapshot(resized, { 800, 600 }, 2202));
    assert(!state.beginSnapshot(resized, 200)); // Monotonic clock regression.
    assert(state.beginSnapshot(resized, 2301));
    assert(!state.finishSnapshot(resized, { 800, 600 }, 2300));

    assert(state.beginSnapshot(resized, 2401));
    state.invalidate(); // Navigation, suspension, visibility loss or destruction.
    assert(!state.current(resized));
    assert(!state.finishSnapshot(resized, { 800, 600 }, 2402));
    assert(!state.beginSnapshot(resized, 2501));
    const auto replacement = state.reset({ 2048, 2048 }, true);
    assert(replacement && replacement != resized);
    assert(state.beginSnapshot(replacement, 2501));
    assert(state.finishSnapshot(replacement, { 2048, 2048 }, 2502));
}
