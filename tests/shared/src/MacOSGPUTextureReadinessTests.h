//
//  MacOSGPUTextureReadinessTests.h
//  tests/shared/src
//
//  Copyright 2026 Overte e.V.
//  SPDX-License-Identifier: Apache-2.0
//

#pragma once

#include <QtTest/QtTest>

class MacOSGPUTextureReadinessTests : public QObject {
    Q_OBJECT

private slots:
    void testRejectsUnstableAllocation();
    void testRejectsPendingTransfer();
    void testRequiresPopulatedMemoryOnHardware();
    void testAcceptsPopulatedMemoryOnHardware();
    void testAcceptsStableSoftwareRendererAllocation();
    void testSoftwareRendererDetectionIsNarrow();
};
