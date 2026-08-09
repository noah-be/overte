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
    return 0;
}
