#include "OpenXrEventPolicy.h"

#include <cassert>

int main() {
    assert(openXrEventDrainAction(false) ==
           OpenXrEventDrainAction::PollNext);
    assert(openXrEventDrainAction(true) ==
           OpenXrEventDrainAction::Stop);

    assert(openXrContextValidAfterEventProcessing(true, true));
    assert(!openXrContextValidAfterEventProcessing(true, false));
    assert(!openXrContextValidAfterEventProcessing(false, true));
    assert(!openXrContextValidAfterEventProcessing(false, false));
    for (unsigned int mask = 0; mask < 8; ++mask) {
        const bool processingSucceeded = (mask & 1U) != 0;
        const bool contextValid = (mask & 2U) != 0;
        const bool frameCycleRequested = (mask & 4U) != 0;
        assert(openXrFrameCycleAllowedAfterEventProcessing(
                   processingSucceeded, contextValid,
                   frameCycleRequested) == (mask == 7U));
    }
    for (unsigned int mask = 0; mask < 8; ++mask) {
        const bool stateContextValid = (mask & 1U) != 0;
        const bool sessionRunning = (mask & 2U) != 0;
        const bool stateAllowsFrames = (mask & 4U) != 0;
        assert(openXrFrameCycleAllowedForSessionState(
                   stateContextValid, sessionRunning,
                   stateAllowsFrames) == (mask == 7U));
    }
    assert(openXrFrameCycleAllowedForSessionState(true, true, true));
    assert(!openXrFrameCycleAllowedForSessionState(true, false, true));
    assert(!openXrFrameCycleAllowedForSessionState(false, true, true));
    bool contextValid = true;
    bool frameCycleRequested = true;
    contextValid = openXrContextValidAfterEventProcessing(
        contextValid, false);
    frameCycleRequested = openXrFrameCycleAllowedAfterEventProcessing(
        false, contextValid, frameCycleRequested);
    assert(!contextValid);
    assert(!frameCycleRequested);
    contextValid = openXrContextValidAfterEventProcessing(
        contextValid, true);
    assert(!contextValid);
    assert(!openXrFrameCycleAllowedForSessionState(
        contextValid, true, true));
    contextValid = true;
    const bool sessionRunning = true;
    assert(openXrFrameCycleAllowedForSessionState(
        contextValid, sessionRunning, true));

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
