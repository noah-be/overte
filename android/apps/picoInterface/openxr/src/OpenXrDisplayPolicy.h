#pragma once

#include <cstddef>
#include <cstdint>

constexpr int64_t OPENXR_NO_SWAPCHAIN_FORMAT = -1;
constexpr std::size_t OPENXR_STEREO_VIEW_COUNT = 2;

inline bool isSupportedOpenXrViewCount(std::size_t count) {
    return count == OPENXR_STEREO_VIEW_COUNT;
}

inline bool isCompleteOpenXrStereoViewResult(
        std::size_t capacity, std::size_t returnedCount) {
    return isSupportedOpenXrViewCount(capacity) && returnedCount == capacity;
}

inline bool isOpenXrSwapchainImageIndexValid(
        std::size_t index, std::size_t imageCount) {
    return index < imageCount;
}

inline bool isConsistentOpenXrEnumerationCount(
        std::size_t capacity, std::size_t returnedCount) {
    return capacity > 0 && returnedCount > 0 && returnedCount <= capacity;
}

inline int64_t selectOpenXrSwapchainFormat(
        const int64_t* formats, std::size_t count, int64_t preferred) {
    if (formats == nullptr || count == 0) {
        return OPENXR_NO_SWAPCHAIN_FORMAT;
    }

    for (std::size_t i = 0; i < count; ++i) {
        if (formats[i] == preferred) {
            return preferred;
        }
    }
    return formats[0];
}
