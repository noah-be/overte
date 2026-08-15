//
//  MacOSOnlineLoadingTelemetryTests.h
//  tests/shared/src
//
//  Copyright 2026 Overte e.V.
//  SPDX-License-Identifier: Apache-2.0
//

#pragma once

#include <QtTest/QtTest>

class MacOSOnlineLoadingTelemetryTests : public QObject {
    Q_OBJECT

private slots:
    void cleanup();
    void testRequiresExplicitTestGate();
    void testRejectsUnsafeIdentity();
    void testEmitsSanitizedMonotonicJSON();
    void testRequiresStrictOrderAndMonotonicTime();
    void testDeduplicatesPerNavigation();
};
