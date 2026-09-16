// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <map>
#include <tuple>

namespace gpu { namespace vk {

// Render-thread cache of exact draw slices in the uploaded index snapshot.
// The owner must invalidate on every staging update, including same-size writes.
class IndexRangeCache {
public:
    struct Range {
        uint32_t minimum { UINT32_MAX };
        uint32_t maximum { 0 };
        bool hasVertices { false };
    };

    void invalidate() { _ranges.clear(); }

    bool get(const uint8_t* data, size_t size, size_t offset, uint32_t first,
             uint32_t count, size_t width, bool restart, Range& result) {
        if (!data || (width != 2 && width != 4) || offset % width != 0 ||
                offset > size || first > (size - offset) / width ||
                count > (size - offset) / width - first) {
            return false;
        }
        const auto key = std::make_tuple(size, offset, first, count, width, restart);
        auto found = _ranges.find(key);
        if (found != _ranges.end()) {
            result = found->second;
            return true;
        }
        Range range;
        const uint32_t sentinel = width == 2 ? UINT16_MAX : UINT32_MAX;
        const uint8_t* selected = data + offset + size_t(first) * width;
        for (uint32_t i = 0; i < count; ++i) {
            uint32_t value;
            if (width == 2) {
                uint16_t narrow;
                std::memcpy(&narrow, selected + size_t(i) * width, sizeof(narrow));
                value = narrow;
            } else {
                std::memcpy(&value, selected + size_t(i) * width, sizeof(value));
            }
            if (restart && value == sentinel) {
                continue;
            }
            range.minimum = std::min(range.minimum, value);
            range.maximum = std::max(range.maximum, value);
            range.hasVertices = true;
        }
        // Bound metadata for dynamic procedural batches with unique slices.
        if (_ranges.size() >= 4096) { _ranges.clear(); }
        _ranges.emplace(key, range);
        result = range;
        return true;
    }

private:
    using Key = std::tuple<size_t, size_t, uint32_t, uint32_t, size_t, bool>;
    std::map<Key, Range> _ranges;
};

} }
