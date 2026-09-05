// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../../interface/src/ApplicationLifecycle.h"
#include <QGuiApplication>
#include <cassert>

namespace { overte::lifecycle::Gate sharedGate; unsigned accesses = 0; }
namespace overte::lifecycle {
// The production definition lives in General's Application.cpp. Substitute
// only that owner definition for this focused test, not the transition class.
Gate& applicationGate() { ++accesses; return sharedGate; }
}
int main(int argc, char** argv) {
    // A deliberately stale pre-start observation must be reconciled with Qt.
    sharedGate.visible(true);
    QGuiApplication app(argc, argv);
    assert(accesses == 0);
    QCoreApplication::processEvents();
    assert(accesses == 1);
    assert(sharedGate.snapshot().foreground ==
           (QGuiApplication::applicationState() == Qt::ApplicationActive));
    QCoreApplication::processEvents();
    assert(accesses == 1); // native startup does not compete with recurring Shared actions
}
