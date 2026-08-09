#pragma once

#include <cstddef>
#include <cstdint>
#include <cmath>
#include <vector>

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

constexpr bool isOpenXrSwapchainImageWaitComplete(
        bool resultSucceeded, bool timeoutExpired) {
    return resultSucceeded && !timeoutExpired;
}

constexpr bool isOpenXrFramePresentationComplete(
        bool imagesReleased, bool endFrameSucceeded) {
    return imagesReleased && endFrameSucceeded;
}

constexpr bool shouldSubmitOpenXrProjectionLayer(
        bool shouldRender, bool viewsUsable, bool imagesReleased) {
    return shouldRender && viewsUsable && imagesReleased;
}

enum class OpenXrSessionChildCleanup {
    Noop,
    ClearOnly,
    DestroyAndClear,
};

constexpr OpenXrSessionChildCleanup openXrSessionChildCleanup(
        bool handleIsNonNull, bool sessionIsAlive) {
    return !handleIsNonNull ? OpenXrSessionChildCleanup::Noop
        : (sessionIsAlive ? OpenXrSessionChildCleanup::DestroyAndClear
                          : OpenXrSessionChildCleanup::ClearOnly);
}

inline bool isOpenXrFoveationProfileUsable(
        bool createSucceeded, bool handleIsNonNull) {
    return createSucceeded && handleIsNonNull;
}

inline bool isConsistentOpenXrEnumerationCount(
        std::size_t capacity, std::size_t returnedCount) {
    return capacity > 0 && returnedCount > 0 && returnedCount <= capacity;
}

inline bool isOpenXrEnumerationCountWithinCapacity(
        std::size_t capacity, std::size_t returnedCount) {
    return returnedCount <= capacity;
}

constexpr bool isOpenXrLocatedPoseUsable(
        bool locateSucceeded,
        std::uint64_t actualFlags,
        std::uint64_t requiredFlags) {
    return locateSucceeded &&
        (actualFlags & requiredFlags) == requiredFlags;
}

constexpr bool isOpenXrViewStateUsable(
        std::uint64_t actualFlags,
        std::uint64_t requiredFlags) {
    return (actualFlags & requiredFlags) == requiredFlags;
}

inline float selectLowestUsableOpenXrRefreshRate(
        const float* rates, std::size_t count) {
    if (rates == nullptr || count == 0) {
        return 0.0f;
    }
    float selected = 0.0f;
    for (std::size_t i = 0; i < count; ++i) {
        const float rate = rates[i];
        if (!std::isfinite(rate) || rate <= 0.0f) {
            continue;
        }
        if (selected == 0.0f || rate < selected) {
            selected = rate;
        }
    }
    return selected;
}

template<typename Handle, typename Destroy>
inline bool destroyOpenXrHandles(
        std::vector<Handle>& handles, Handle nullHandle, Destroy destroy) {
    bool succeeded = true;
    for (Handle& handle : handles) {
        if (handle == nullHandle) {
            continue;
        }
        if (!destroy(handle)) {
            succeeded = false;
        }
        handle = nullHandle;
    }
    return succeeded;
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
