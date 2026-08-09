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
