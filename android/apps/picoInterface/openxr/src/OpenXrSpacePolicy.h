#pragma once

enum class OpenXrWorldSpaceChoice { Stage, Local, Unavailable };

constexpr OpenXrWorldSpaceChoice openXrWorldSpaceChoice(
        bool stageAvailable, bool localAvailable) {
    return stageAvailable ? OpenXrWorldSpaceChoice::Stage
            : (localAvailable ? OpenXrWorldSpaceChoice::Local
                              : OpenXrWorldSpaceChoice::Unavailable);
}
