// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <limits>

namespace image {
// Check BEFORE generateImageDescriptors(), whose cube arithmetic uses uint32.
// This path supports ordinary 2D/cube assets, not array/volume textures.
template<class Header> std::uint64_t checkedKtxPlaceholderBytes(const Header& h) {
    if (!h.pixelWidth || h.pixelWidth > 16384 || h.pixelHeight > 16384 ||
        h.pixelDepth > 1 || h.numberOfArrayElements != 0 ||
        (h.numberOfFaces != 1 && h.numberOfFaces != 6) ||
        !h.numberOfMipmapLevels || h.numberOfMipmapLevels > 15 ||
        h.bytesOfKeyValueData > 65536) { return 0; }
    const auto bits = h.evalPixelOrBlockBitSize();
    if (!bits || bits > 128) { return 0; }
    // Reserve enough for the appended minMip key and alignment.
    std::uint64_t bytes = 64 + std::uint64_t(h.bytesOfKeyValueData) + 64;
    for (std::uint32_t level = 0; level < h.numberOfMipmapLevels; ++level) {
        const std::uint64_t face = h.evalFaceSize(level);
        if (!face || face > (std::numeric_limits<std::uint32_t>::max() - 3ULL) / h.numberOfFaces) { return 0; }
        const auto imageBytes = face * h.numberOfFaces;
        bytes += 4 + ((imageBytes + 3) & ~std::uint64_t(3));
    }
    return bytes;
}
inline bool ktxPlaceholderFits(std::uint64_t bytes, std::uint64_t availableBytes) {
    constexpr std::uint64_t LIMIT = 128ULL * 1024 * 1024;
    constexpr std::uint64_t RESERVE = 512ULL * 1024 * 1024;
    return bytes && bytes <= LIMIT && availableBytes >= RESERVE && bytes <= availableBytes - RESERVE;
}
}
