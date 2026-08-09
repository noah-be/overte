#include "OpenXrInputPolicy.h"

#include <limits>
#include <string>

#include "test_assertions.h"

int main() {
    OVERTE_EXPECT(std::string(OPENXR_VIVE_TRACKER_WAIST_POSE_PATH) ==
                  "/user/vive_tracker_htcx/role/waist/input/grip/pose");
    OVERTE_EXPECT(std::string(OPENXR_VIVE_TRACKER_CHEST_POSE_PATH) ==
                  "/user/vive_tracker_htcx/role/chest/input/grip/pose");
    OVERTE_EXPECT(std::string(OPENXR_VIVE_TRACKER_LEFT_FOOT_POSE_PATH) ==
                  "/user/vive_tracker_htcx/role/left_foot/input/grip/pose");
    OVERTE_EXPECT(std::string(OPENXR_VIVE_TRACKER_RIGHT_FOOT_POSE_PATH) ==
                  "/user/vive_tracker_htcx/role/right_foot/input/grip/pose");

    OVERTE_EXPECT(!openXrVirtualTriggerPressed(false, 1.0f));
    OVERTE_EXPECT(!openXrVirtualTriggerPressed(true, 0.0f));
    OVERTE_EXPECT(!openXrVirtualTriggerPressed(true,
            OPENXR_VIRTUAL_TRIGGER_CLICK_THRESHOLD - 0.0001f));
    OVERTE_EXPECT(openXrVirtualTriggerPressed(true,
            OPENXR_VIRTUAL_TRIGGER_CLICK_THRESHOLD));
    OVERTE_EXPECT(openXrVirtualTriggerPressed(true, 1.0f));
    OVERTE_EXPECT(!openXrVirtualTriggerPressed(
            true, std::numeric_limits<float>::quiet_NaN()));
    OVERTE_EXPECT(openXrVirtualTriggerPressed(
            true, std::numeric_limits<float>::infinity()));

    OVERTE_EXPECT(OpenXrHapticNone == openXrHapticTargets(false, 0));
    OVERTE_EXPECT(OpenXrHapticNone == openXrHapticTargets(false, 2));
    OVERTE_EXPECT(OpenXrHapticLeft == openXrHapticTargets(true, 0));
    OVERTE_EXPECT(OpenXrHapticRight == openXrHapticTargets(true, 1));
    OVERTE_EXPECT((OpenXrHapticLeft | OpenXrHapticRight)
            == openXrHapticTargets(true, 2));
    OVERTE_EXPECT(OpenXrHapticNone == openXrHapticTargets(true, 3));
    OVERTE_EXPECT(OpenXrHapticNone == openXrHapticTargets(true, 65535));

    for (unsigned int mask = 0; mask < 16; ++mask) {
        const bool hasSpace = (mask & 1U) != 0;
        const bool hasAction = (mask & 2U) != 0;
        const bool sessionAlive = (mask & 4U) != 0;
        const bool instanceAlive = (mask & 8U) != 0;
        const unsigned int expected =
            (hasSpace && sessionAlive ? OpenXrActionCleanupSpace : 0U) |
            (hasAction && instanceAlive ? OpenXrActionCleanupAction : 0U);
        OVERTE_EXPECT(openXrActionCleanupTargets(
            hasSpace, hasAction, sessionAlive, instanceAlive) == expected);
    }

    OVERTE_EXPECT(!openXrHandJointOutputUsable(false, false));
    OVERTE_EXPECT(!openXrHandJointOutputUsable(false, true));
    OVERTE_EXPECT(!openXrHandJointOutputUsable(true, false));
    OVERTE_EXPECT(openXrHandJointOutputUsable(true, true));

    constexpr unsigned long long position = 1ULL << 0;
    constexpr unsigned long long orientation = 1ULL << 1;
    constexpr unsigned long long tracked = 1ULL << 2;
    constexpr unsigned long long pose = position | orientation;
    OVERTE_EXPECT(!openXrHandJointFlagsSatisfy(0, pose));
    OVERTE_EXPECT(!openXrHandJointFlagsSatisfy(position, pose));
    OVERTE_EXPECT(!openXrHandJointFlagsSatisfy(orientation, pose));
    OVERTE_EXPECT(openXrHandJointFlagsSatisfy(pose, pose));
    OVERTE_EXPECT(openXrHandJointFlagsSatisfy(pose | tracked, pose));
    OVERTE_EXPECT(openXrHandJointFlagsSatisfy(orientation, orientation));
    OVERTE_EXPECT(!openXrHandJointFlagsSatisfy(position, orientation));
    OVERTE_EXPECT(openXrHandJointFlagsSatisfy(0, 0));
    OVERTE_EXPECT(!openXrPoseFlagsSatisfy(0, pose));
    OVERTE_EXPECT(!openXrPoseFlagsSatisfy(position, pose));
    OVERTE_EXPECT(!openXrPoseFlagsSatisfy(orientation, pose));
    OVERTE_EXPECT(openXrPoseFlagsSatisfy(pose, pose));
    OVERTE_EXPECT(openXrPoseFlagsSatisfy(pose | tracked, pose));

    for (unsigned int mask = 0; mask < 16; ++mask) {
        OVERTE_EXPECT(openXrPoseActionCanLocate(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0,
                   (mask & 4U) != 0,
                   (mask & 8U) != 0) == (mask == 15U));
    }

    for (unsigned int mask = 0; mask < 8; ++mask) {
        OVERTE_EXPECT(openXrXDevRoleSamplingReady(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0,
                   (mask & 4U) != 0) == (mask == 7U));
    }

    constexpr unsigned long long positionValid = 1ULL << 4;
    constexpr unsigned long long otherFlag = 1ULL << 5;
    OVERTE_EXPECT(openXrXDevRoleLocationsUsable(
        true, positionValid, true, positionValid, true, positionValid,
        positionValid));
    OVERTE_EXPECT(openXrXDevRoleLocationsUsable(
        true, positionValid | otherFlag, true, positionValid | otherFlag,
        true, positionValid | otherFlag, positionValid));
    for (unsigned int missing = 0; missing < 6; ++missing) {
        OVERTE_EXPECT(!openXrXDevRoleLocationsUsable(
            missing != 0, missing == 1 ? 0 : positionValid,
            missing != 2, missing == 3 ? 0 : positionValid,
            missing != 4, missing == 5 ? 0 : positionValid,
            positionValid));
    }

    const float nan = std::numeric_limits<float>::quiet_NaN();
    const float infinity = std::numeric_limits<float>::infinity();
    OVERTE_EXPECT(openXrXDevRoleDimensionsUsable(-0.2f, 0.1f, 1.7f));
    OVERTE_EXPECT(openXrXDevRoleDimensionsUsable(0.0f, 0.0f, 1.7f));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(0.0f, 1.0f, 0.0f));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(0.0f, 1.0f, -1.0f));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(nan, 1.0f, 1.0f));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(0.0f, nan, 1.0f));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(0.0f, 1.0f, nan));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(infinity, 1.0f, 1.0f));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(0.0f, infinity, 1.0f));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(0.0f, 1.0f, infinity));
    OVERTE_EXPECT(!openXrXDevRoleDimensionsUsable(
        0.0f, 1.0f, std::numeric_limits<float>::denorm_min()));

    OVERTE_EXPECT(classifyOpenXrXDevRole(-0.1f, 0.19f) ==
                  OpenXrXDevRole::LeftFoot);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.19f) ==
                  OpenXrXDevRole::RightFoot);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.1f, 0.19f) ==
                  OpenXrXDevRole::RightFoot);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.2f) == OpenXrXDevRole::None);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.4f) == OpenXrXDevRole::None);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.4001f) == OpenXrXDevRole::Hips);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.6499f) == OpenXrXDevRole::Hips);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.65f) == OpenXrXDevRole::None);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.6501f) == OpenXrXDevRole::Chest);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.8999f) == OpenXrXDevRole::Chest);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, 0.9f) == OpenXrXDevRole::None);
    OVERTE_EXPECT(classifyOpenXrXDevRole(nan, 0.1f) == OpenXrXDevRole::None);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, nan) == OpenXrXDevRole::None);
    OVERTE_EXPECT(classifyOpenXrXDevRole(infinity, 0.1f) == OpenXrXDevRole::None);
    OVERTE_EXPECT(classifyOpenXrXDevRole(0.0f, infinity) == OpenXrXDevRole::None);

    OVERTE_EXPECT(!openXrBoundedEnumerationUsable(false, 0, 16));
    OVERTE_EXPECT(openXrBoundedEnumerationUsable(true, 0, 16));
    OVERTE_EXPECT(openXrBoundedEnumerationUsable(true, 1, 16));
    OVERTE_EXPECT(openXrBoundedEnumerationUsable(true, 16, 16));
    OVERTE_EXPECT(!openXrBoundedEnumerationUsable(true, 17, 16));
    OVERTE_EXPECT(!openXrBoundedEnumerationUsable(false, 1, 16));
    OVERTE_EXPECT(openXrBoundedEnumerationUsable(true, 0, 0));
    const auto maximum = std::numeric_limits<std::size_t>::max();
    OVERTE_EXPECT(openXrBoundedEnumerationUsable(true, maximum, maximum));
    OVERTE_EXPECT(!openXrBoundedEnumerationUsable(true, maximum, maximum - 1));

    OVERTE_EXPECT(!openXrCreatedHandleUsable(false, false));
    OVERTE_EXPECT(!openXrCreatedHandleUsable(false, true));
    OVERTE_EXPECT(!openXrCreatedHandleUsable(true, false));
    OVERTE_EXPECT(openXrCreatedHandleUsable(true, true));

    for (unsigned int mask = 0; mask < 4; ++mask) {
        OVERTE_EXPECT(openXrPathConversionUsable(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0) == (mask == 3U));
    }

    OVERTE_EXPECT(openXrLocatedPoseUsable(true, true, true, pose, pose));
    OVERTE_EXPECT(!openXrLocatedPoseUsable(false, true, true, pose, pose));
    OVERTE_EXPECT(!openXrLocatedPoseUsable(true, false, true, pose, pose));
    OVERTE_EXPECT(!openXrLocatedPoseUsable(true, true, false, pose, pose));
    OVERTE_EXPECT(!openXrLocatedPoseUsable(true, true, true, 0, pose));
    OVERTE_EXPECT(!openXrLocatedPoseUsable(true, true, true, position, pose));
    OVERTE_EXPECT(!openXrLocatedPoseUsable(true, true, true, orientation, pose));
    OVERTE_EXPECT(openXrLocatedPoseUsable(
        true, true, true, pose | tracked, pose));
    OVERTE_EXPECT(openXrLocatedPoseUsable(
        true, true, true, std::numeric_limits<unsigned long long>::max(), pose));

    OVERTE_EXPECT(openXrOwnedHandleCleanup(false, false) ==
                  OpenXrOwnedHandleCleanup::Noop);
    OVERTE_EXPECT(openXrOwnedHandleCleanup(false, true) ==
                  OpenXrOwnedHandleCleanup::Noop);
    OVERTE_EXPECT(openXrOwnedHandleCleanup(true, false) ==
                  OpenXrOwnedHandleCleanup::ClearOnly);
    OVERTE_EXPECT(openXrOwnedHandleCleanup(true, true) ==
                  OpenXrOwnedHandleCleanup::DestroyAndClear);
    return 0;
}
