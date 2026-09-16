// SPDX-License-Identifier: Apache-2.0
#include "interface/src/ApplicationLifecycle.h"
#include <cassert>
#include <thread>
using namespace overte::lifecycle;
int main() {
    Gate gate;
    assert(!gate.begin(1, 0).accepted);
    auto visible = gate.visible(true);
    assert(visible.accepted && visible.snapshot.state == State::Idle);
    assert(!gate.visible(true).accepted);
    assert(!gate.begin(0, 0).accepted);
    auto first = gate.begin(1, 100);
    assert(first.accepted && first.action == Action::Connect && first.snapshot.attempts == 1);
    assert(!gate.begin(1, 101).accepted);
    assert(!gate.connected(first.snapshot.generation - 1, 101).accepted);
    assert(!gate.connected(first.snapshot.generation, 99).accepted);
    assert(gate.connected(first.snapshot.generation, 101).accepted);
    auto recovery = gate.lost(first.snapshot.generation);
    assert(recovery.accepted && recovery.snapshot.state == State::Recovery);
    assert(!gate.lost(first.snapshot.generation).accepted);
    auto second = gate.retry(recovery.snapshot.generation, 200);
    assert(second.accepted && second.action == Action::Retry && second.snapshot.attempts == 2);
    assert(!gate.connected(first.snapshot.generation, 201).accepted);
    assert(!gate.timeout(second.snapshot.generation, 15199).accepted);
    recovery = gate.timeout(second.snapshot.generation, 15200);
    assert(recovery.accepted && recovery.snapshot.state == State::Recovery);
    auto third = gate.retry(recovery.snapshot.generation, 15300);
    assert(third.accepted && third.snapshot.attempts == 3);
    assert(!gate.connected(third.snapshot.generation, 30300).accepted);
    auto failed = gate.timeout(third.snapshot.generation, 30300);
    assert(failed.accepted && failed.snapshot.state == State::Failed);
    assert(!gate.retry(failed.snapshot.generation, 31000).accepted);
    assert(!gate.begin(1, 31000).accepted); // duplicate cannot reset retry budget
    auto replacement = gate.begin(2, 32000);
    assert(replacement.accepted && replacement.snapshot.attempts == 1);
    auto suspended = gate.visible(false);
    assert(suspended.accepted && suspended.action == Action::Cancel);
    assert(!gate.connected(replacement.snapshot.generation, 32001).accepted);
    assert(!gate.begin(3, 32002).accepted);
    gate.visible(true);
    assert(gate.snapshot().state == State::Idle); // no unsolicited resume/reconnect
    assert(!gate.begin(3, 1).accepted); // regressing clock
    assert(!gate.begin(3, UINT64_MAX).accepted); // overflow
    assert(gate.begin(3, 33000).accepted);
    gate.stop();
    assert(!gate.visible(true).accepted && !gate.begin(4, 34000).accepted);
    assert(!gate.stop().accepted);
    Gate concurrent;
    std::thread reader([&] { for (int i = 0; i < 10000; ++i) { concurrent.snapshot(); } });
    for (int i = 0; i < 10000; ++i) { concurrent.visible(i % 2); }
    reader.join();
}
