#pragma once

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
