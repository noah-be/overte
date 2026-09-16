// SPDX-License-Identifier: Apache-2.0
#include "interface/src/avatar/PhoneSpawnGate.h"
#include <cassert>

int main() {
    PhoneSpawnGate gate;
    assert(!gate.held());
    gate.begin(100);
    assert(gate.held());
    assert(!gate.update(101, false, true)); // stale collider, new world not ready
    assert(gate.held());
    assert(!gate.update(129.9, true, false)); // rendering/loading alone cannot release
    assert(gate.held());
    assert(gate.update(130, true, false)); // one actionable timeout
    assert(gate.held()); // a timeout never authorizes a fall
    assert(!gate.update(131, true, false));
    assert(!gate.update(132, true, true)); // late support safely recovers
    assert(!gate.held());
    gate.begin(200); // new destination re-arms after a successful entry
    assert(gate.held());
    gate.begin(220); // navigation while waiting replaces the previous timeout
    assert(!gate.update(231, false, false));
    assert(gate.held());
    assert(gate.update(250, false, false));
    gate.begin(251); // retry after failed entry
    assert(!gate.update(252, true, true));
    assert(!gate.held());
}
