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

    for (unsigned int mask = 0; mask < 4; ++mask) {
        assert(isOpenXrPathReady(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0) == (mask == 3U));
    }
    for (unsigned int mask = 0; mask < 16; ++mask) {
        assert(areOpenXrRequiredHandPathsReady(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0,
                   (mask & 4U) != 0,
                   (mask & 8U) != 0) == (mask == 15U));
    }

    for (unsigned int mask = 0; mask < 4; ++mask) {
        assert(areOpenXrDebugMessengerFunctionsReady(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0) == (mask == 3U));
    }

    for (unsigned int mask = 0; mask < 8; ++mask) {
        assert(areOpenXrRefreshRateFunctionsReady(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0,
                   (mask & 4U) != 0) == (mask == 7U));
    }

    for (unsigned int mask = 0; mask < 8; ++mask) {
        assert(areOpenXrFoveationFunctionsReady(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0,
                   (mask & 4U) != 0) == (mask == 7U));
    }

    for (unsigned int mask = 0; mask < 32; ++mask) {
        assert(areOpenXrXDevFunctionsReady(
                   (mask & 1U) != 0,
                   (mask & 2U) != 0,
                   (mask & 4U) != 0,
                   (mask & 8U) != 0,
                   (mask & 16U) != 0) == (mask == 31U));
    }

    for (unsigned int mask = 0; mask < 8; ++mask) {
        const bool viveSupported = (mask & 1U) != 0;
        const bool viveFunctionReady = (mask & 2U) != 0;
        const bool mndxReady = (mask & 4U) != 0;
        const auto expected = viveSupported && viveFunctionReady
            ? OpenXrBodyTrackingBackend::Vive
            : (mndxReady ? OpenXrBodyTrackingBackend::Mndx
                         : OpenXrBodyTrackingBackend::None);
        assert(selectOpenXrBodyTrackingBackend(
                   viveSupported, viveFunctionReady, mndxReady) == expected);
    }

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
