// SPDX-License-Identifier: Apache-2.0
#include "libraries/audio-client/src/PicoCapturePolicy.h"
#include <cassert>
#include <thread>
int main() {
    overte::audio::PicoCapturePolicy policy;
    assert(!policy.allows() && !policy.accepts(0));
    assert(!policy.change(false));
    assert(policy.change(true));
    auto initial = policy.ticket();
    assert(policy.accepts(initial));
    assert(!policy.change(true) && policy.accepts(initial));
    assert(policy.change(false) && !policy.accepts(initial));
    assert(policy.change(true) && !policy.accepts(initial));
    assert(policy.accepts(policy.ticket()));
    std::thread reader([&] { for (int i = 0; i < 10000; ++i) { policy.accepts(initial); } });
    for (int i = 0; i < 10000; ++i) { policy.change(i % 2); }
    reader.join();
    policy.change(false);
    assert(!policy.allows());
}
