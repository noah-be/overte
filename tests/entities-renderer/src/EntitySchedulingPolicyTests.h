//
//  EntitySchedulingPolicyTests.h
//
//  Copyright 2026 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#pragma once

#include <QtTest/QtTest>

class EntitySchedulingPolicyTests : public QObject {
    Q_OBJECT

private slots:
    void safeLandingPrioritizesCollidableEntities();
    void unbudgetedUpdateHonorsCostAndCountBoundaries();
};
