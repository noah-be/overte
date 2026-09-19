// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "AndroidStartupUrlPolicy.h"
#include "support/test_assertions.h"

int main() {
    using android::startup::Destination;
    using android::startup::selectDestination;

    // Explicit URLs override this launch without changing persistent first-run state.
    OVERTE_EXPECT(selectDestination(true, true) == Destination::ExplicitUrl);
    OVERTE_EXPECT(selectDestination(false, true) == Destination::ExplicitUrl);

    // Fresh profiles get the common Android tutorial entry point. Empty and
    // invalid launch URLs are represented by hasExplicitUrl=false.
    OVERTE_EXPECT(selectDestination(true, false) == Destination::FirstRunOrDefault);

    // Later launches use AddressManager's saved/home settings and its default
    // address if the setting is absent. No Pico-only fixture is a fallback.
    OVERTE_EXPECT(selectDestination(false, false) == Destination::SavedAddress);

    static_assert(selectDestination(true, true) == Destination::ExplicitUrl,
        "an explicit URL must have exactly one startup destination");

    return 0;
}
