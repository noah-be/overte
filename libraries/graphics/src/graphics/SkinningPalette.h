// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#ifndef overte_graphics_SkinningPalette_h
#define overte_graphics_SkinningPalette_h

#include <array>
#include <cstddef>
#include <cstring>
#include <vector>
#include <glm/glm.hpp>
#include <gpu/Buffer.h>
#include "ShaderConstants.h"

namespace graphics {
// Matches Skinning.slh std140 layout. Always bind the complete declared block;
// shader loads are additionally bounded by the actual populated entry count.
struct alignas(16) SkinningPalette {
    std::array<gpu::Byte, GRAPHICS_MAX_SKINNING_CLUSTERS * 64> clusters {};
    glm::uvec4 info;
};
static_assert(offsetof(SkinningPalette, info) == GRAPHICS_MAX_SKINNING_CLUSTERS * 64);
static_assert(sizeof(SkinningPalette) == GRAPHICS_MAX_SKINNING_CLUSTERS * 64 + 16);

template<class Entry>
bool updateSkinningPalette(gpu::BufferPointer& buffer, const std::vector<Entry>& entries, size_t expectedCount) {
    static_assert(sizeof(Entry) == sizeof(glm::mat4), "Skinning entry must occupy four vec4 columns");
    if (entries.size() != expectedCount || entries.size() > GRAPHICS_MAX_SKINNING_CLUSTERS) {
        buffer.reset(); // Never retain a stale, differently mapped palette.
        return false;
    }
    SkinningPalette palette;
    palette.info = glm::uvec4(uint32_t(entries.size()), 0, 0, 0);
    // Copy object representations to bytes, never construct GLM/DQ objects by memcpy.
    if (!entries.empty()) { std::memcpy(palette.clusters.data(), entries.data(), entries.size() * sizeof(Entry)); }
    if (!buffer) { buffer = std::make_shared<gpu::Buffer>(gpu::Buffer::UniformBuffer); }
    buffer->setData(sizeof(palette), reinterpret_cast<const gpu::Byte*>(&palette));
    return true;
}
}
#endif
