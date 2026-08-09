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
    assert(!isOpenXrSwapchainImageIndexValid(0, 0));
    assert(isOpenXrSwapchainImageIndexValid(0, 1));
    assert(!isOpenXrSwapchainImageIndexValid(1, 1));
    assert(isOpenXrSwapchainImageIndexValid(7, 8));
    assert(!isOpenXrSwapchainImageIndexValid(8, 8));
    assert(!isOpenXrSwapchainImageIndexValid(9, 8));
    assert(!isOpenXrSwapchainImageIndexValid(
        std::numeric_limits<std::size_t>::max(), 8));
    assert(isOpenXrSwapchainImageIndexValid(
        0, std::numeric_limits<std::size_t>::max()));
    assert(!isConsistentOpenXrEnumerationCount(0, 0));
    assert(!isConsistentOpenXrEnumerationCount(0, 1));
    assert(!isConsistentOpenXrEnumerationCount(1, 0));
    assert(isConsistentOpenXrEnumerationCount(1, 1));
    assert(isConsistentOpenXrEnumerationCount(3, 1));
    assert(isConsistentOpenXrEnumerationCount(3, 3));
    assert(!isConsistentOpenXrEnumerationCount(3, 4));
    const std::size_t maximum = std::numeric_limits<std::size_t>::max();
    assert(isConsistentOpenXrEnumerationCount(maximum, maximum));
    assert(!isConsistentOpenXrEnumerationCount(maximum - 1, maximum));

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
