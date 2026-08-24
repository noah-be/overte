//
//  MacOSGPUTextureReadinessTests.cpp
//  tests/shared/src
//
//  Copyright 2026 Overte e.V.
//  SPDX-License-Identifier: Apache-2.0
//

#include "MacOSGPUTextureReadinessTests.h"

#include <MacOSGPUTextureReadiness.h>

namespace readiness = macos::gpu_texture_readiness;

QTEST_MAIN(MacOSGPUTextureReadinessTests)

void MacOSGPUTextureReadinessTests::testRejectsUnstableAllocation() {
    QVERIFY(!readiness::isComplete(29, 30, 100, 100, 0, "Apple Software Renderer"));
}

void MacOSGPUTextureReadinessTests::testRejectsPendingTransfer() {
    QVERIFY(!readiness::isComplete(30, 30, 100, 80, 1, "Apple Software Renderer"));
}

void MacOSGPUTextureReadinessTests::testRequiresPopulatedMemoryOnHardware() {
    QVERIFY(!readiness::isComplete(30, 30, 100, 80, 0, "AMD Radeon Pro 5500M OpenGL Engine"));
}

void MacOSGPUTextureReadinessTests::testAcceptsPopulatedMemoryOnHardware() {
    QVERIFY(readiness::isComplete(30, 30, 100, 100, 0, "Apple M2"));
}

void MacOSGPUTextureReadinessTests::testAcceptsStableSoftwareRendererAllocation() {
    QVERIFY(readiness::isComplete(30, 30, 100, 80, 0, "Apple Software Renderer"));
}

void MacOSGPUTextureReadinessTests::testSoftwareRendererDetectionIsNarrow() {
    QVERIFY(readiness::usesStableAllocationFallback("Apple Software Renderer"));
    QVERIFY(!readiness::usesStableAllocationFallback("Apple M2"));
    QVERIFY(!readiness::usesStableAllocationFallback("llvmpipe"));
    QVERIFY(!readiness::usesStableAllocationFallback("SwiftShader"));
}
