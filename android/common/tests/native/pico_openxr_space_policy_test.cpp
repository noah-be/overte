#include "OpenXrSpacePolicy.h"

#include <vector>

#include "test_assertions.h"

int main() {
    for (unsigned int mask = 0; mask < 8; ++mask) {
        const bool viewSpaceNonNull = (mask & 1U) != 0;
        const bool worldSpaceNonNull = (mask & 2U) != 0;
        const bool sessionNonNull = (mask & 4U) != 0;
        OVERTE_EXPECT(mask == openXrPostGraphicsCleanupTargets(
            viewSpaceNonNull, worldSpaceNonNull, sessionNonNull));
    }

    const unsigned int allTargets = openXrPostGraphicsCleanupTargets(
        true, true, true);
    std::vector<unsigned int> cleanupOrder;
    if ((allTargets & OpenXrPostGraphicsCleanupViewSpace) != 0) {
        cleanupOrder.push_back(OpenXrPostGraphicsCleanupViewSpace);
    }
    if ((allTargets & OpenXrPostGraphicsCleanupWorldSpace) != 0) {
        cleanupOrder.push_back(OpenXrPostGraphicsCleanupWorldSpace);
    }
    if ((allTargets & OpenXrPostGraphicsCleanupSession) != 0) {
        cleanupOrder.push_back(OpenXrPostGraphicsCleanupSession);
    }
    OVERTE_EXPECT((cleanupOrder == std::vector<unsigned int> {
        OpenXrPostGraphicsCleanupViewSpace,
        OpenXrPostGraphicsCleanupWorldSpace,
        OpenXrPostGraphicsCleanupSession,
    }));
    OVERTE_EXPECT(OpenXrPostGraphicsCleanupNone ==
        openXrPostGraphicsCleanupTargets(false, false, false));

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
