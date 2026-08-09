#pragma once

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
