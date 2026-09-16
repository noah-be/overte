// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace overte::ios {
// Numeric, process-local evidence only. No names, URLs, pointers or content IDs.
// A draw attempt is not proof that a command executed or caused a GPU fault.
struct GpuDrawAttempt {
    uint64_t frame {}, batch {}, ordinal {};
    uint32_t command {}, vertexShader {}, fragmentShader {};
    uint64_t first {}, count {}, instances {}, firstInstance {}, minimumIndex {}, maximumIndex {};
    bool inputChecked {}, inputValid {}, indexed {}, hasVertices {};
};
class GpuDrawBreadcrumbs {
public:
    static constexpr size_t CAPACITY = 128;
    struct Snapshot {
        uint64_t submit {}, total {};
        size_t size {};
        std::array<GpuDrawAttempt, CAPACITY> draws {};
    };
    void attempt(const GpuDrawAttempt& draw) noexcept {
        _encoding.draws[_encoding.total % CAPACITY] = draw;
        ++_encoding.total;
        if (_encoding.size < CAPACITY) { ++_encoding.size; }
    }
    void input(bool indexed, uint64_t first, uint64_t count, uint64_t instances,
               uint64_t firstInstance, bool valid, bool hasVertices,
               uint64_t minimum, uint64_t maximum) noexcept {
        if (!_encoding.total) { return; }
        auto& draw = _encoding.draws[(_encoding.total - 1) % CAPACITY];
        draw.inputChecked = true; draw.inputValid = valid; draw.indexed = indexed;
        draw.first = first; draw.count = count; draw.instances = instances;
        draw.firstInstance = firstInstance; draw.hasVertices = hasVertices;
        draw.minimumIndex = minimum; draw.maximumIndex = maximum;
    }
    void submit(uint64_t id) noexcept {
        _pending = _encoding; _pending.submit = id;
        _encoding.total = 0; _encoding.size = 0;
    }
    void retire() noexcept { _pending = {}; }
    const Snapshot& pending() const noexcept { return _pending; }
    static const GpuDrawAttempt& at(const Snapshot& s, size_t index) noexcept {
        const auto oldest = s.total > CAPACITY ? s.total % CAPACITY : 0;
        return s.draws[(oldest + index) % CAPACITY];
    }
private:
    Snapshot _encoding {}, _pending {};
};
}
