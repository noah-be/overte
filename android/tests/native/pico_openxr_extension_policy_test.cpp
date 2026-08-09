#include "OpenXrExtensionPolicy.h"

#include <cassert>

int main() {
    for (unsigned int mask = 0; mask < 8; ++mask) {
        const bool createLoaded = (mask & 1U) != 0;
        const bool destroyLoaded = (mask & 2U) != 0;
        const bool locateLoaded = (mask & 4U) != 0;
        assert(areOpenXrHandTrackingFunctionsReady(
                   createLoaded, destroyLoaded, locateLoaded) == (mask == 7U));
    }

    assert(!isOpenXrOptionalFunctionReady(false, false));
    assert(!isOpenXrOptionalFunctionReady(false, true));
    assert(!isOpenXrOptionalFunctionReady(true, false));
    assert(isOpenXrOptionalFunctionReady(true, true));

    assert(openXrHandTrackerPairState(false, false) ==
           OpenXrHandTrackerPairState::None);
    assert(openXrHandTrackerPairState(true, false) ==
           OpenXrHandTrackerPairState::Partial);
    assert(openXrHandTrackerPairState(false, true) ==
           OpenXrHandTrackerPairState::Partial);
    assert(openXrHandTrackerPairState(true, true) ==
           OpenXrHandTrackerPairState::Complete);
    return 0;
}
