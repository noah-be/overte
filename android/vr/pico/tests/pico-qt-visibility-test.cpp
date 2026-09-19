// SPDX-License-Identifier: Apache-2.0
#include "../../../../interface/src/PicoQtVisibility.h"
#include "../../../../interface/src/ApplicationLifecycle.h"
#include <cassert>
int main() {
    using namespace overte;
    pico::VisibilityInputs awaitingNative;
    assert(!awaitingNative.observeQt(pico::qtVisible(Qt::ApplicationActive)));
    assert(!awaitingNative.observeQt(pico::qtVisible(Qt::ApplicationInactive)));
    assert(awaitingNative.observeNative(true));
    assert(!awaitingNative.observeNative(false));
    for (auto state : {Qt::ApplicationSuspended, Qt::ApplicationHidden,
                       Qt::ApplicationInactive, Qt::ApplicationActive}) {
        pico::VisibilityInputs inputs;
        inputs.observeNative(false);
        assert(!inputs.observeQt(pico::qtVisible(state)));
        const bool visible = state == Qt::ApplicationInactive || state == Qt::ApplicationActive;
        assert(inputs.observeNative(true) == visible);
        assert(!inputs.observeNative(false));
    }
    pico::VisibilityInputs inputs;
    inputs.observeNative(true);
    assert(inputs.observeQt(pico::qtVisible(Qt::ApplicationInactive)));
    assert(!inputs.observeQt(pico::qtVisible(Qt::ApplicationHidden)));
    assert(inputs.observeQt(pico::qtVisible(Qt::ApplicationActive)));
    assert(!inputs.observeQt(pico::qtVisible(Qt::ApplicationSuspended)));
}
