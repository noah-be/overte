#include "OpenXrEventPolicy.h"

#include <cassert>

int main() {
    assert(openXrEventDrainAction(false) ==
           OpenXrEventDrainAction::PollNext);
    assert(openXrEventDrainAction(true) ==
           OpenXrEventDrainAction::Stop);

    assert(!isOpenXrPathStringUsable(false, 1, 8, true));
    assert(!isOpenXrPathStringUsable(true, 0, 8, true));
    assert(!isOpenXrPathStringUsable(true, 9, 8, true));
    assert(!isOpenXrPathStringUsable(true, 1, 8, false));
    assert(isOpenXrPathStringUsable(true, 1, 8, true));
    assert(isOpenXrPathStringUsable(true, 8, 8, true));
    assert(!openXrSessionRunningAfterTermination(false, false));
    assert(openXrSessionRunningAfterTermination(true, false));
    assert(!openXrSessionRunningAfterTermination(false, true));
    assert(!openXrSessionRunningAfterTermination(true, true));

    const bool events[] = { false, false, true, false };
    unsigned int processed = 0;
    unsigned int nextPolls = 0;
    for (bool instanceLossPending : events) {
        ++processed;
        if (openXrEventDrainAction(instanceLossPending) ==
                OpenXrEventDrainAction::Stop) {
            break;
        }
        ++nextPolls;
    }
    assert(processed == 3);
    assert(nextPolls == 2);
    return 0;
}
