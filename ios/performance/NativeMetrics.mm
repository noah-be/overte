// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "NativeMetrics.h"
#import <Foundation/Foundation.h>
#import <mach/mach.h>

namespace overte::ios {
NativeMetrics sampleNativeMetrics() noexcept {
    NativeMetrics result;
    task_vm_info_data_t vm {};
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, reinterpret_cast<task_info_t>(&vm), &count) == KERN_SUCCESS &&
        count >= TASK_VM_INFO_REV1_COUNT && vm.phys_footprint > 0) {
        result.footprintAvailable = true;
        result.footprintBytes = vm.phys_footprint;
    }
    @autoreleasepool {
      @try {
        NSProcessInfo* process = NSProcessInfo.processInfo;
        if (process == nil) { return result; }
        result.lowPower = process.lowPowerModeEnabled;
        result.lowPowerAvailable = true;
        switch (process.thermalState) {
            case NSProcessInfoThermalStateNominal: result.thermal = ThermalState::Nominal; break;
            case NSProcessInfoThermalStateFair: result.thermal = ThermalState::Fair; break;
            case NSProcessInfoThermalStateSerious: result.thermal = ThermalState::Serious; break;
            case NSProcessInfoThermalStateCritical: result.thermal = ThermalState::Critical; break;
            default: break;
        }
      } @catch (NSException*) {
        result.lowPowerAvailable = false;
        result.lowPower = false;
        result.thermal = ThermalState::Unknown;
      }
    }
    return result;
}

} // namespace overte::ios
