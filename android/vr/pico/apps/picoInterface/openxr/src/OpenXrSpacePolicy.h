#pragma once

enum class OpenXrWorldSpaceChoice { Stage, Local, Unavailable };

enum OpenXrPostGraphicsCleanupTarget : unsigned int {
    OpenXrPostGraphicsCleanupNone = 0,
    OpenXrPostGraphicsCleanupViewSpace = 1,
    OpenXrPostGraphicsCleanupWorldSpace = 2,
    OpenXrPostGraphicsCleanupSession = 4,
};

constexpr unsigned int openXrPostGraphicsCleanupTargets(
        bool viewSpaceNonNull,
        bool worldSpaceNonNull,
        bool sessionNonNull) {
    return (viewSpaceNonNull ? OpenXrPostGraphicsCleanupViewSpace
                             : OpenXrPostGraphicsCleanupNone) |
        (worldSpaceNonNull ? OpenXrPostGraphicsCleanupWorldSpace
                           : OpenXrPostGraphicsCleanupNone) |
        (sessionNonNull ? OpenXrPostGraphicsCleanupSession
                        : OpenXrPostGraphicsCleanupNone);
}

constexpr OpenXrWorldSpaceChoice openXrWorldSpaceChoice(
        bool stageAvailable, bool localAvailable) {
    return stageAvailable ? OpenXrWorldSpaceChoice::Stage
            : (localAvailable ? OpenXrWorldSpaceChoice::Local
                              : OpenXrWorldSpaceChoice::Unavailable);
}
