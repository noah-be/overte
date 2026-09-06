// SPDX-License-Identifier: Apache-2.0
#include "../../apps/phoneInterface/src/PhonePendingNavigation.h"
#include <cassert>
#include <string>
#include <iostream>

int main() {
    using namespace overte::lifecycle;
    Gate gate; // Test-only instance; production uses applicationGate().
    phone::PendingNavigation<std::string> pending(gate);
    std::string output = "unchanged";
    pending.replace("synthetic destination", true);
    assert(!pending.takeIfReady(true, output));
    assert(output == "unchanged");
    gate.visible(true);
    pending.replace("first", true);
    assert(!pending.takeIfReady(false, output));
    pending.replace("latest", true);
    gate.visible(true); // duplicate does not invalidate this generation
    assert(pending.takeIfReady(true, output) && output == "latest");
    assert(!pending.takeIfReady(true, output));
    assert(gate.snapshot().state == State::Idle); // Not a fabricated connection.
    pending.replace("cancelled", true);
    gate.visible(false);
    gate.visible(true);
    assert(!pending.takeIfReady(true, output) && output == "latest");
    pending.replace("replacement", true);
    assert(pending.takeIfReady(true, output) && output == "replacement");
    pending.replace("stale callback", true);
    gate.begin(1, 100); // any newer attempt generation cancels the old callback
    assert(!pending.takeIfReady(true, output));
    pending.replace("invalid", false);
    assert(!pending.takeIfReady(true, output));
    pending.replace("cleared", true);
    pending.clear();
    assert(!pending.takeIfReady(true, output));
    pending.replace("stopped", true);
    gate.stop();
    assert(!pending.takeIfReady(true, output));
    std::cout << "Phone SH-005 pending navigation cancellation PASS\n";
}
