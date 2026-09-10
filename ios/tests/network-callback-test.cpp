// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../networking/CallbackEpoch.h"
#include <cassert>
#include <thread>
#include <vector>
using overte::ios::CallbackEpoch;
int main() {
    CallbackEpoch owner;
    auto first = owner.begin();
    assert(first.current());
    auto second = owner.begin();
    assert(!first.current() && second.current());
    owner.cancel();
    assert(!second.current());
    owner.cancel();
    auto current = owner.begin();
    std::vector<std::thread> callbacks;
    owner.cancel();
    for (int i = 0; i < 32; ++i) {
        callbacks.emplace_back([current] { assert(!current.current()); });
    }
    for (auto& t : callbacks) { t.join(); }
    auto expired = [] { CallbackEpoch temporary; return temporary.begin(); }();
    assert(!expired.current());
    auto newest = owner.begin();
    assert(newest.current() && !current.current());
}
