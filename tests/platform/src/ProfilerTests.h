// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <QtTest/QtTest>

class ProfilerTests : public QObject {
    Q_OBJECT
private slots:
    void testMacGPUClassification();
};
