#include "OpenXrEventPolicy.h"

#include <cassert>

int main() {
    assert(openXrEventDrainAction(false) ==
           OpenXrEventDrainAction::PollNext);
    assert(openXrEventDrainAction(true) ==
           OpenXrEventDrainAction::Stop);

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
