// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMetrics.h"

namespace overte::ios {
// The original Shared publisher owns the cross-platform fields and validation.
bool publishNativeMetrics(const NativeMetrics& native, bool foreground);
}
