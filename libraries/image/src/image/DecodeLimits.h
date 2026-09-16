// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <limits>

namespace image {
// A zero budget preserves existing desktop policy. Validate before allocation;
// division avoids overflow even for corrupt EXR window dimensions.
inline bool decodedImageFits(std::int64_t width, std::int64_t height, std::uint64_t maxPixels) {
    return width > 0 && height > 0 &&
        width <= std::numeric_limits<int>::max() && height <= std::numeric_limits<int>::max() &&
        (!maxPixels || static_cast<std::uint64_t>(width) <= maxPixels / static_cast<std::uint64_t>(height));
}
}
