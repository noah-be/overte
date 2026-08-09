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
    return 0;
}
