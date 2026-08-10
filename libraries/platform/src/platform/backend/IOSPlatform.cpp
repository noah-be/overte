// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "IOSPlatform.h"

#include "../PlatformKeys.h"

#include <thread>

#include <QSysInfo>

using namespace platform;

void IOSInstance::enumerateCpus() {
    json cpu = {};
    cpu[keys::cpu::vendor] = keys::computer::vendor_Apple;
    cpu[keys::cpu::model] = QSysInfo::currentCpuArchitecture().toStdString();
    cpu[keys::cpu::numCores] = std::thread::hardware_concurrency();
    _cpus.push_back(cpu);
}

void IOSInstance::enumerateGpusAndDisplays() {
    // UIKit and Metal own device/display discovery on iOS. The desktop CGL
    // inventory has no safe equivalent at this platform abstraction boundary.
}

void IOSInstance::enumerateMemory() {
    _memory = { { keys::memory::memTotal, 0 } };
}

void IOSInstance::enumerateComputer() {
    _computer[keys::computer::OS] = keys::computer::OS_IOS;
    _computer[keys::computer::vendor] = keys::computer::vendor_Apple;
    _computer[keys::computer::model] = keys::UNKNOWN;
    _computer[keys::computer::OSVersion] = QSysInfo::productVersion().toStdString();
}

void IOSInstance::enumerateGraphicsApis() {
    // Do not call the generic GL/Vulkan probe before the iOS renderer owns a
    // valid surface. Renderer telemetry is collected at its native boundary.
}
