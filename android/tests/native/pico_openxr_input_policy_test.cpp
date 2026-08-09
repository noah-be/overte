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
    return 0;
}
