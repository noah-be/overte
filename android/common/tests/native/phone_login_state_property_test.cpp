#include <array>
#include <cstdint>

#include "PhoneLoginState.h"
#include "test_assertions.h"

namespace {

uint64_t next(uint64_t& state) {
    state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    return state;
}

} // namespace

int main() {
    std::array<PhoneLoginState, 8> actual;
    std::array<bool, 8> expected {{ false, false, false, false, false, false, false, false }};
    uint64_t randomState { UINT64_C(0x4c4f47494e535441) };

    for (int step = 0; step < 8192; ++step) {
        const std::size_t instance = static_cast<std::size_t>(next(randomState) % actual.size());
        if ((next(randomState) & 3U) == 0U) {
            // Success, failure, and cancel all deliver the same terminal state
            // transition at this policy boundary.
            actual[instance].finishRequest();
            expected[instance] = false;
        } else {
            const bool accepted = actual[instance].beginRequest();
            OVERTE_EXPECT(accepted == !expected[instance]);
            expected[instance] = true;
        }
        for (std::size_t index = 0; index < actual.size(); ++index) {
            OVERTE_EXPECT(actual[index].requestPending() == expected[index]);
        }
    }
    return 0;
}
