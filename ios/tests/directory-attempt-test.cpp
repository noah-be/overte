// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../networking/DirectoryAttempt.h"
#include <cassert>
using namespace overte::ios;
using overte::lifecycle::State;
int main() {
    DirectoryAttempt attempt;
    assert(attempt.begin(0) == 0);
    attempt.visible(true);
    const auto first = attempt.begin(10);
    assert(first && !attempt.complete(first, 15010)); // exact deadline rejected
    assert(attempt.snapshot().state == State::Recovery);
    const auto second = attempt.retry(15011);
    assert(second && second != first);
    assert(!attempt.complete(first, 15012));
    attempt.failed(second);
    const auto third = attempt.retry(15013);
    assert(third && attempt.snapshot().attempts == 3);
    attempt.failed(third);
    assert(attempt.snapshot().state == State::Failed && attempt.retry(15014) == 0);
    const auto editedIntent = attempt.begin(15015);
    assert(editedIntent && attempt.snapshot().attempts == 1);
    attempt.visible(false);
    assert(!attempt.complete(editedIntent, 15016));
    attempt.visible(true);
    assert(attempt.snapshot().state == State::Idle);
    const auto resumed = attempt.begin(15017);
    assert(resumed && attempt.complete(resumed, 15018));
    attempt.cancel();
    assert(attempt.snapshot().state == State::Recovery);
    attempt.stop();
    assert(attempt.begin(15019) == 0 && attempt.snapshot().state == State::Stopped);
}
