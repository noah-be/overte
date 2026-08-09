#include "OpenXrSpacePolicy.h"

#include "test_assertions.h"

int main() {
    OVERTE_EXPECT(OpenXrWorldSpaceChoice::Stage ==
            openXrWorldSpaceChoice(true, true));
    OVERTE_EXPECT(OpenXrWorldSpaceChoice::Stage ==
            openXrWorldSpaceChoice(true, false));
    OVERTE_EXPECT(OpenXrWorldSpaceChoice::Local ==
            openXrWorldSpaceChoice(false, true));
    OVERTE_EXPECT(OpenXrWorldSpaceChoice::Unavailable ==
            openXrWorldSpaceChoice(false, false));
    return 0;
}
