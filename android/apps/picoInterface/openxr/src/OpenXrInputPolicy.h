#pragma once

#include <cstddef>

constexpr float OPENXR_VIRTUAL_TRIGGER_CLICK_THRESHOLD = 0.95f;

constexpr bool openXrVirtualTriggerPressed(bool active, float value) {
    return active && value >= OPENXR_VIRTUAL_TRIGGER_CLICK_THRESHOLD;
}

enum OpenXrHapticTarget : unsigned int {
    OpenXrHapticNone = 0,
    OpenXrHapticLeft = 1,
    OpenXrHapticRight = 2,
};

constexpr unsigned int openXrHapticTargets(bool enabled, unsigned int index) {
    return !enabled || index > 2 ? OpenXrHapticNone
            : (index == 0 ? OpenXrHapticLeft
                          : (index == 1 ? OpenXrHapticRight
                                        : OpenXrHapticLeft | OpenXrHapticRight));
}

constexpr bool openXrHandJointOutputUsable(
        bool locateSucceeded, bool isActive) {
    return locateSucceeded && isActive;
}

constexpr bool openXrHandJointFlagsSatisfy(
        unsigned long long actualFlags, unsigned long long requiredFlags) {
    return (actualFlags & requiredFlags) == requiredFlags;
}

constexpr bool openXrBoundedEnumerationUsable(
        bool callSucceeded, std::size_t returnedCount, std::size_t capacity) {
    return callSucceeded && returnedCount <= capacity;
}

constexpr bool openXrCreatedHandleUsable(
        bool callSucceeded, bool handleIsNonNull) {
    return callSucceeded && handleIsNonNull;
}

constexpr bool openXrLocatedPoseUsable(
        bool spaceIsNonNull,
        bool predictionAvailable,
        bool locateSucceeded,
        unsigned long long actualFlags,
        unsigned long long requiredFlags) {
    return spaceIsNonNull && predictionAvailable && locateSucceeded &&
        openXrHandJointFlagsSatisfy(actualFlags, requiredFlags);
}
