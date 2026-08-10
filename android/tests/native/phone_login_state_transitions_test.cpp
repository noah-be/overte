#include "PhoneLoginState.h"
#include "test_assertions.h"

int main() {
    PhoneLoginState state;

    OVERTE_EXPECT(!state.requestPending());

    for (int request = 0; request < 100; ++request) {
        OVERTE_EXPECT(state.beginRequest());
        OVERTE_EXPECT(state.requestPending());

        // Every competing submission is rejected until terminal delivery.
        for (int duplicate = 0; duplicate < 10; ++duplicate) {
            OVERTE_EXPECT(!state.beginRequest());
            OVERTE_EXPECT(state.requestPending());
        }

        state.finishRequest();
        OVERTE_EXPECT(!state.requestPending());
    }

    // Terminal delivery is deliberately idempotent, including before the
    // first request and after an already completed request.
    state.finishRequest();
    state.finishRequest();
    OVERTE_EXPECT(!state.requestPending());
    OVERTE_EXPECT(state.beginRequest());

    return 0;
}
