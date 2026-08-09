#include "OpenXrDisplayPolicy.h"

#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

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
    assert(!isOpenXrSwapchainImageWaitComplete(false, false));
    assert(!isOpenXrSwapchainImageWaitComplete(false, true));
    assert(!isOpenXrSwapchainImageWaitComplete(true, true));
    assert(isOpenXrSwapchainImageWaitComplete(true, false));
    assert(!isOpenXrFramePresentationComplete(false));
    assert(isOpenXrFramePresentationComplete(true));
    assert(!isOpenXrFoveationProfileUsable(false, false));
    assert(!isOpenXrFoveationProfileUsable(false, true));
    assert(!isOpenXrFoveationProfileUsable(true, false));
    assert(isOpenXrFoveationProfileUsable(true, true));
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
    assert(isOpenXrEnumerationCountWithinCapacity(0, 0));
    assert(!isOpenXrEnumerationCountWithinCapacity(0, 1));
    assert(isOpenXrEnumerationCountWithinCapacity(1, 0));
    assert(isOpenXrEnumerationCountWithinCapacity(1, 1));
    assert(isOpenXrEnumerationCountWithinCapacity(3, 1));
    assert(isOpenXrEnumerationCountWithinCapacity(3, 3));
    assert(!isOpenXrEnumerationCountWithinCapacity(3, 4));
    assert(isOpenXrEnumerationCountWithinCapacity(maximum, maximum));
    assert(!isOpenXrEnumerationCountWithinCapacity(maximum - 1, maximum));

    constexpr std::uint64_t positionValid = 1ULL << 0;
    constexpr std::uint64_t orientationValid = 1ULL << 1;
    constexpr std::uint64_t tracked = 1ULL << 2;
    constexpr std::uint64_t requiredPose = positionValid | orientationValid;
    assert(!isOpenXrLocatedPoseUsable(false, 0, requiredPose));
    assert(!isOpenXrLocatedPoseUsable(false, requiredPose, requiredPose));
    assert(!isOpenXrLocatedPoseUsable(true, 0, requiredPose));
    assert(!isOpenXrLocatedPoseUsable(true, positionValid, requiredPose));
    assert(!isOpenXrLocatedPoseUsable(true, orientationValid, requiredPose));
    assert(isOpenXrLocatedPoseUsable(true, requiredPose, requiredPose));
    assert(isOpenXrLocatedPoseUsable(
        true, requiredPose | tracked, requiredPose));
    assert(!isOpenXrLocatedPoseUsable(true, tracked, requiredPose));
    assert(isOpenXrLocatedPoseUsable(true, 0, 0));
    assert(!isOpenXrLocatedPoseUsable(false, 0, 0));
    assert(!isOpenXrViewStateUsable(0, requiredPose));
    assert(!isOpenXrViewStateUsable(positionValid, requiredPose));
    assert(!isOpenXrViewStateUsable(orientationValid, requiredPose));
    assert(isOpenXrViewStateUsable(requiredPose, requiredPose));
    assert(isOpenXrViewStateUsable(
        requiredPose | tracked, requiredPose));
    assert(!isOpenXrViewStateUsable(tracked, requiredPose));
    assert(isOpenXrViewStateUsable(0, 0));

    assert(selectLowestUsableOpenXrRefreshRate(nullptr, 0) == 0.0f);
    assert(selectLowestUsableOpenXrRefreshRate(nullptr, 2) == 0.0f);
    const float oneRate[] = { 72.0f };
    assert(selectLowestUsableOpenXrRefreshRate(oneRate, 1) == 72.0f);
    const float rates[] = { 90.0f, 72.0f, 72.0f, 120.0f };
    assert(selectLowestUsableOpenXrRefreshRate(rates, 4) == 72.0f);
    const float invalidRates[] = {
        0.0f, -72.0f, std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()
    };
    assert(selectLowestUsableOpenXrRefreshRate(invalidRates, 5) == 0.0f);
    const float mixedRates[] = {
        std::numeric_limits<float>::quiet_NaN(), 90.0f, 72.0f,
        std::numeric_limits<float>::infinity()
    };
    assert(selectLowestUsableOpenXrRefreshRate(mixedRates, 4) == 72.0f);
    const float smallestPositive[] = {
        90.0f, std::numeric_limits<float>::min(), 72.0f
    };
    assert(selectLowestUsableOpenXrRefreshRate(smallestPositive, 3) ==
           std::numeric_limits<float>::min());

    std::vector<int> handles = { 11, 0, 22, 33 };
    std::vector<int> destroyed;
    bool cleanupSucceeded = destroyOpenXrHandles(handles, 0, [&](int handle) {
        destroyed.push_back(handle);
        return handle != 22;
    });
    assert(!cleanupSucceeded);
    assert((destroyed == std::vector<int> { 11, 22, 33 }));
    assert((handles == std::vector<int> { 0, 0, 0, 0 }));
    destroyed.clear();
    assert(destroyOpenXrHandles(handles, 0, [&](int handle) {
        destroyed.push_back(handle);
        return true;
    }));
    assert(destroyed.empty());

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
