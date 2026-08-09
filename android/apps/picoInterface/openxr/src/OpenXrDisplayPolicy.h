#pragma once

#include <cstddef>
#include <cstdint>

constexpr int64_t OPENXR_NO_SWAPCHAIN_FORMAT = -1;

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
