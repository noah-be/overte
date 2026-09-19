// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtCore/Qt>
#include "ApplicationLifecycle.h"

namespace overte { namespace pico {
// Qt Inactive is visible without keyboard focus. The native resumed Activity
// remains an additional veto in VisibilityInputs; Hidden/Suspended deny here.
constexpr bool qtVisible(Qt::ApplicationState state) noexcept {
    return state == Qt::ApplicationActive || state == Qt::ApplicationInactive;
}
// A visible Qt surface alone cannot authorize a Pico launch before the native
// Activity has supplied its first observation. A native pause always vetoes.
class VisibilityInputs {
public:
    bool observeQt(bool visible) {
        const bool effective = _inputs.observeQt(visible);
        return _nativeSeen && effective;
    }
    bool observeNative(bool resumed) {
        _nativeSeen = true;
        return _inputs.observeNative(resumed);
    }
private:
    bool _nativeSeen { false };
    lifecycle::VisibilityInputs _inputs;
};
}} // namespace overte::pico
