#pragma once

#include <cstddef>
#include <cmath>

constexpr float OPENXR_VIRTUAL_TRIGGER_CLICK_THRESHOLD = 0.95f;

constexpr const char OPENXR_VIVE_TRACKER_WAIST_POSE_PATH[] =
    "/user/vive_tracker_htcx/role/waist/input/grip/pose";
constexpr const char OPENXR_VIVE_TRACKER_CHEST_POSE_PATH[] =
    "/user/vive_tracker_htcx/role/chest/input/grip/pose";
constexpr const char OPENXR_VIVE_TRACKER_LEFT_FOOT_POSE_PATH[] =
    "/user/vive_tracker_htcx/role/left_foot/input/grip/pose";
constexpr const char OPENXR_VIVE_TRACKER_RIGHT_FOOT_POSE_PATH[] =
    "/user/vive_tracker_htcx/role/right_foot/input/grip/pose";

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

constexpr bool openXrPoseFlagsSatisfy(
        unsigned long long actualFlags, unsigned long long requiredFlags) {
    return (actualFlags & requiredFlags) == requiredFlags;
}

constexpr bool openXrHandJointFlagsSatisfy(
        unsigned long long actualFlags, unsigned long long requiredFlags) {
    return openXrPoseFlagsSatisfy(actualFlags, requiredFlags);
}

constexpr bool openXrPoseActionCanLocate(
        bool actionStateSucceeded,
        bool actionIsActive,
        bool poseSpaceIsNonNull,
        bool predictionAvailable) {
    return actionStateSucceeded && actionIsActive && poseSpaceIsNonNull &&
        predictionAvailable;
}

constexpr bool openXrXDevRoleSamplingReady(
        bool xdevCapabilityReady,
        bool predictionAvailable,
        bool hasTrackers) {
    return xdevCapabilityReady && predictionAvailable && hasTrackers;
}

constexpr bool openXrXDevRoleLocationsUsable(
        bool stageLocateSucceeded,
        unsigned long long stageFlags,
        bool localLocateSucceeded,
        unsigned long long localFlags,
        bool headLocateSucceeded,
        unsigned long long headFlags,
        unsigned long long positionValidBit) {
    return stageLocateSucceeded && localLocateSucceeded && headLocateSucceeded &&
        (stageFlags & positionValidBit) != 0 &&
        (localFlags & positionValidBit) != 0 &&
        (headFlags & positionValidBit) != 0;
}

inline bool openXrXDevRoleDimensionsUsable(
        float localX, float stageHeight, float headHeight) {
    return std::isfinite(localX) && std::isfinite(stageHeight) &&
        std::isfinite(headHeight) && headHeight > 0.0f &&
        std::isfinite(stageHeight / headHeight);
}

enum class OpenXrXDevRole {
    None,
    LeftFoot,
    RightFoot,
    Hips,
    Chest,
};

inline OpenXrXDevRole classifyOpenXrXDevRole(
        float localX, float normalizedHeight) {
    if (!std::isfinite(localX) || !std::isfinite(normalizedHeight)) {
        return OpenXrXDevRole::None;
    }
    if (normalizedHeight < 0.2f) {
        return localX < 0.0f ? OpenXrXDevRole::LeftFoot
                             : OpenXrXDevRole::RightFoot;
    }
    if (normalizedHeight > 0.4f && normalizedHeight < 0.65f) {
        return OpenXrXDevRole::Hips;
    }
    if (normalizedHeight > 0.65f && normalizedHeight < 0.9f) {
        return OpenXrXDevRole::Chest;
    }
    return OpenXrXDevRole::None;
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
        openXrPoseFlagsSatisfy(actualFlags, requiredFlags);
}

enum class OpenXrOwnedHandleCleanup {
    Noop,
    ClearOnly,
    DestroyAndClear,
};

constexpr OpenXrOwnedHandleCleanup openXrOwnedHandleCleanup(
        bool handleIsNonNull, bool owningSessionIsAlive) {
    return !handleIsNonNull ? OpenXrOwnedHandleCleanup::Noop
        : (owningSessionIsAlive ? OpenXrOwnedHandleCleanup::DestroyAndClear
                               : OpenXrOwnedHandleCleanup::ClearOnly);
}
