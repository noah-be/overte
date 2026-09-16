// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PhonePendingHandoff.h"
#include "../../../../../interface/src/ApplicationLifecycle.h"

namespace phone {
// Local queue ownership only. State/generation come from original SH-005,
// never a copied lifecycle machine or an inferred successful connection.
template<typename Value>
class PendingNavigation {
public:
    explicit PendingNavigation(overte::lifecycle::Gate& gate) : _gate(gate) { }
    void replace(Value value, bool valid) {
        const auto snapshot = _gate.snapshot();
        _generation = snapshot.generation;
        _pending.replace(std::move(value), valid && snapshot.foreground);
    }
    bool takeIfReady(bool ready, Value& output) {
        const auto snapshot = _gate.snapshot();
        if (!snapshot.foreground || snapshot.generation != _generation) {
            _pending.clear();
            return false;
        }
        return _pending.takeIfReady(ready, output);
    }
    void clear() { _pending.clear(); }
private:
    overte::lifecycle::Gate& _gate;
    PendingHandoff<Value> _pending;
    std::uint64_t _generation { 0 };
};
}
