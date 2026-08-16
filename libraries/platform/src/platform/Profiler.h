//
//  Profiler.h
//  libraries/platform/src/platform
//
//  Created by Sam Gateau on 5/22/2019.
//  Copyright 2019 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#ifndef hifi_platform_Profiler_h
#define hifi_platform_Profiler_h

#include <array>
#include <string>

namespace platform {

class Profiler {
public:
    enum Tier {
        UNKNOWN = 0,
        LOW_POWER,
        LOW,
        MID,
        HIGH,
        CUSTOM, // Never used, added for consistency with performance presets

        NumTiers, // not a valid Tier
    };
    static const std::array<const char*, Tier::NumTiers> TierNames;

    static Tier profilePlatform();

    // Deterministic macOS GPU policy, exposed for platform regression tests.
    // Virtual/software renderers must start conservatively; hardware vendors
    // retain the established Intel=LOW, other=MID behavior until measured
    // native-hardware profiles provide a stronger policy.
    static Tier profileMacGPU(const std::string& vendor, const std::string& model);

    // Ugly very adhoc capability check to know if a particular hw can REnder with Deferred method or not
    static bool isRenderMethodDeferredCapable();
};

}
#endif
