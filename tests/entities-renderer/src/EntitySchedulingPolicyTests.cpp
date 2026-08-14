//
//  EntitySchedulingPolicyTests.cpp
//
//  Copyright 2026 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "EntitySchedulingPolicyTests.h"

#include <EntitySchedulingPolicy.h>

QTEST_MAIN(EntitySchedulingPolicyTests)

void EntitySchedulingPolicyTests::safeLandingPrioritizesCollidableEntities() {
    constexpr auto collidable = EntitySchedulingPolicy::safeLandingLoadPriority(false);
    constexpr auto collisionless = EntitySchedulingPolicy::safeLandingLoadPriority(true);

    QCOMPARE(collidable, 10.0f);
    QCOMPARE(collisionless, 0.0f);
    QVERIFY(collidable > collisionless);
}

void EntitySchedulingPolicyTests::unbudgetedUpdateHonorsCostAndCountBoundaries() {
    using EntitySchedulingPolicy::shouldUseUnbudgetedRenderableUpdate;

    QVERIFY(shouldUseUnbudgetedRenderableUpdate(1999.0f, 16, 2000));
    QVERIFY(!shouldUseUnbudgetedRenderableUpdate(0.0f, 17, 2000));
    QVERIFY(!shouldUseUnbudgetedRenderableUpdate(2000.0f, 1, 2000));
    QVERIFY(!shouldUseUnbudgetedRenderableUpdate(2001.0f, 1, 2000));
    QVERIFY(shouldUseUnbudgetedRenderableUpdate(0.0f, 0, 2000));
}
