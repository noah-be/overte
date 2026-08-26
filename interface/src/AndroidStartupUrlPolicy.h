//
//  AndroidStartupUrlPolicy.h
//  interface/src
//
//  Copyright 2026 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

#pragma once

namespace android {
namespace startup {

enum class Destination {
    FirstRunOrDefault,
    ExplicitUrl,
    SavedAddress,
};

// This policy deliberately does not mutate first-run state. An explicit URL
// selects only this launch; a later launch without one still gets the normal
// first-run target.
constexpr Destination selectDestination(bool firstRun, bool hasExplicitUrl,
                                        bool hasFallbackAddress) {
    return hasExplicitUrl
        ? Destination::ExplicitUrl
        : (firstRun || !hasFallbackAddress
            ? Destination::FirstRunOrDefault
            : Destination::SavedAddress);
}

} // namespace startup
} // namespace android
