#pragma once

#include <cstddef>

enum class OpenXrEventDrainAction {
    PollNext,
    Stop,
};

constexpr OpenXrEventDrainAction openXrEventDrainAction(
        bool instanceLossPending) {
    return instanceLossPending
        ? OpenXrEventDrainAction::Stop
        : OpenXrEventDrainAction::PollNext;
}

constexpr bool isOpenXrPathStringUsable(
        bool conversionSucceeded,
        std::size_t returnedCount,
        std::size_t capacity,
        bool terminatedWithinReturnedCount) {
    return conversionSucceeded && returnedCount > 0 &&
        returnedCount <= capacity && terminatedWithinReturnedCount;
}

constexpr bool openXrSessionRunningAfterTermination(
        bool currentlyRunning, bool terminationSucceeded) {
    return terminationSucceeded ? false : currentlyRunning;
}
