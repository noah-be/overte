//
//  EntitySchedulingPolicy.h
//
//  Copyright 2026 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#pragma once

#include <cstddef>
#include <cstdint>

namespace EntitySchedulingPolicy {

constexpr float COLLIDABLE_ENTITY_LOAD_PRIORITY { 10.0f };
constexpr std::size_t MAX_UNBUDGETED_RENDERABLE_UPDATES { 16 };

constexpr float safeLandingLoadPriority(bool collisionless) noexcept {
    return collisionless ? 0.0f : COLLIDABLE_ENTITY_LOAD_PRIORITY;
}

constexpr bool shouldUseUnbudgetedRenderableUpdate(float expectedCostUsec,
                                                    std::size_t pendingCount,
                                                    std::uint64_t budgetUsec) noexcept {
    return expectedCostUsec < static_cast<float>(budgetUsec) &&
        pendingCount <= MAX_UNBUDGETED_RENDERABLE_UPDATES;
}

} // namespace EntitySchedulingPolicy
