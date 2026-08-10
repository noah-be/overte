// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "PlatformInstance.h"

namespace platform {

class IOSInstance : public Instance {
public:
    void enumerateCpus() override;
    void enumerateGpusAndDisplays() override;
    void enumerateMemory() override;
    void enumerateComputer() override;
    void enumerateGraphicsApis() override;
};

}  // namespace platform
