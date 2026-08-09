#include <cstdint>
#include <string>

#include "PhonePendingHandoff.h"
#include "test_assertions.h"

namespace {

uint64_t next(uint64_t& state) {
    state = state * UINT64_C(2862933555777941757) + UINT64_C(3037000493);
    return state;
}

} // namespace

int main() {
    phone::PendingHandoff<std::string> handoff;
    bool expectedPending { false };
    std::string expectedValue;
    std::string delivered { "initial" };
    uint64_t state { UINT64_C(0x48414e444f464650) };

    for (int step = 0; step < 4096; ++step) {
        const unsigned operation = static_cast<unsigned>(next(state) % 4U);
        if (operation == 0U) {
            expectedValue = "hifi://generated/" + std::to_string(next(state));
            handoff.replace(expectedValue);
            expectedPending = true;
        } else if (operation == 1U) {
            handoff.replace("ignored", false);
            expectedPending = false;
            expectedValue.clear();
        } else if (operation == 2U) {
            handoff.clear();
            expectedPending = false;
            expectedValue.clear();
        } else {
            const bool ready = (next(state) & 1U) != 0;
            const std::string before = delivered;
            const bool taken = handoff.takeIfReady(ready, delivered);
            OVERTE_EXPECT(taken == (ready && expectedPending));
            if (taken) {
                OVERTE_EXPECT(delivered == expectedValue);
                expectedPending = false;
                expectedValue.clear();
            } else {
                OVERTE_EXPECT(delivered == before);
            }
        }
        OVERTE_EXPECT(handoff.pending() == expectedPending);
    }
    return 0;
}
