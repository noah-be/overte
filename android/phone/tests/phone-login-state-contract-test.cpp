#include <cassert>

#include "PhoneLoginState.h"

int main() {
    PhoneLoginState state;

    // A first request starts, and a competing touch/key/script submission is
    // rejected while it remains unresolved.
    assert(state.beginRequest());
    assert(state.requestPending());
    assert(!state.beginRequest());

    // Dismissing the QML view must not manufacture a terminal network result.
    // Reopening therefore sees the same pending transaction.
    assert(state.requestPending());

    // A late failure or success is terminal and permits a fresh request. The
    // state contract intentionally treats both terminal outcomes identically.
    state.finishRequest();
    assert(!state.requestPending());
    assert(state.beginRequest());
    state.finishRequest();
    assert(!state.requestPending());

    // Duplicate terminal delivery is harmless and cannot create a pending
    // request or poison the next dialog instance.
    state.finishRequest();
    assert(!state.requestPending());
    assert(state.beginRequest());

    return 0;
}
