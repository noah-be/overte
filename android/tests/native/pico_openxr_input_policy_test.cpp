#include "OpenXrInputPolicy.h"

#include <limits>

#include "test_assertions.h"

int main() {
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
    return 0;
}
