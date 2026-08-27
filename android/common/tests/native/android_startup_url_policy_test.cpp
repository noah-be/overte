// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "AndroidStartupUrlPolicy.h"
#include "support/test_assertions.h"

int main() {
    using android::startup::Destination;
    using android::startup::selectDestination;

    // A valid explicit URL wins on both fresh and initialized profiles.
    OVERTE_EXPECT(selectDestination(true, true, true) == Destination::ExplicitUrl);
    OVERTE_EXPECT(selectDestination(false, true, true) == Destination::ExplicitUrl);

    // Empty and invalid URLs are both represented by hasExplicitUrl=false.
    OVERTE_EXPECT(selectDestination(true, false, false) ==
        Destination::FirstRunOrDefault);
    OVERTE_EXPECT(selectDestination(true, false, true) ==
        Destination::FirstRunOrDefault);

    // Android variants without a usable saved address retain their default
    // target, while a non-first-run Pico fallback remains a saved address.
    OVERTE_EXPECT(selectDestination(false, false, false) ==
        Destination::FirstRunOrDefault);
    OVERTE_EXPECT(selectDestination(false, false, true) ==
        Destination::SavedAddress);

    // The selector has one destination and no mutable or persistent state.
    static_assert(selectDestination(true, true, true) == Destination::ExplicitUrl,
        "an explicit URL must have exactly one startup destination");

    return 0;
}
