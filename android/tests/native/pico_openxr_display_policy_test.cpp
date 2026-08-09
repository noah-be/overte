#include "OpenXrDisplayPolicy.h"

#include <cassert>
#include <cstdint>
#include <limits>

int main() {
    assert(!isSupportedOpenXrViewCount(0));
    assert(!isSupportedOpenXrViewCount(1));
    assert(isSupportedOpenXrViewCount(2));
    assert(!isSupportedOpenXrViewCount(3));
    assert(!isSupportedOpenXrViewCount(std::numeric_limits<std::size_t>::max()));
    assert(isCompleteOpenXrStereoViewResult(2, 2));
    assert(!isCompleteOpenXrStereoViewResult(2, 0));
    assert(!isCompleteOpenXrStereoViewResult(2, 1));
    assert(!isCompleteOpenXrStereoViewResult(2, 3));
    assert(!isCompleteOpenXrStereoViewResult(1, 1));

    assert(selectOpenXrSwapchainFormat(nullptr, 0, 7) == OPENXR_NO_SWAPCHAIN_FORMAT);
    assert(selectOpenXrSwapchainFormat(nullptr, 2, 7) == OPENXR_NO_SWAPCHAIN_FORMAT);

    const int64_t formats[] = { 11, 22, 33 };
    assert(selectOpenXrSwapchainFormat(formats, 3, 11) == 11);
    assert(selectOpenXrSwapchainFormat(formats, 3, 22) == 22);
    assert(selectOpenXrSwapchainFormat(formats, 3, 33) == 33);
    assert(selectOpenXrSwapchainFormat(formats, 3, 44) == 11);

    const int64_t single[] = { 55 };
    assert(selectOpenXrSwapchainFormat(single, 1, 44) == 55);

    const int64_t duplicatePreferred[] = { 66, 77, 77 };
    assert(selectOpenXrSwapchainFormat(duplicatePreferred, 3, 77) == 77);
    return 0;
}
