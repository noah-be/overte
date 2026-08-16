// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "ProfilerTests.h"

#include <platform/Profiler.h>

QTEST_MAIN(ProfilerTests)

void ProfilerTests::testMacGPUClassification() {
    using Tier = platform::Profiler::Tier;
    QCOMPARE(platform::Profiler::profileMacGPU("", ""), Tier::LOW);
    QCOMPARE(platform::Profiler::profileMacGPU("Intel", "Iris Plus"), Tier::LOW);
    QCOMPARE(platform::Profiler::profileMacGPU("Apple", "Apple Paravirtualized Graphics Device"),
             Tier::LOW_POWER);
    QCOMPARE(platform::Profiler::profileMacGPU("Apple", "Apple Software Renderer"),
             Tier::LOW_POWER);
    QCOMPARE(platform::Profiler::profileMacGPU("Google", "ANGLE SwiftShader"),
             Tier::LOW_POWER);
    QCOMPARE(platform::Profiler::profileMacGPU("Example", "Virtual GPU"), Tier::LOW_POWER);
    QCOMPARE(platform::Profiler::profileMacGPU("Apple", "Apple M4"), Tier::MID);
    QCOMPARE(platform::Profiler::profileMacGPU("AMD", "Radeon Pro 5600M"), Tier::MID);
}
