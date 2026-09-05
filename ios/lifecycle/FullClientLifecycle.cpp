// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../../interface/src/ApplicationLifecycle.h"
#include <QCoreApplication>
#include <QGuiApplication>
#include <QTimer>

namespace {
void installIOSInitialLifecycle() {
    auto* app = QCoreApplication::instance();
    QTimer::singleShot(0, app, [app] {
        if (!qobject_cast<QGuiApplication*>(app)) { return; }
        // Application's connection observes subsequent state changes. Seed the
        // exact same out-of-line gate if UIKit became active before that hookup.
        // Do not add a competing recurring visibility callback: the first gate
        // caller consumes the transition action, duplicates intentionally do not.
        overte::lifecycle::applicationGate().visible(
            QGuiApplication::applicationState() == Qt::ApplicationActive);
    });
}
}
Q_COREAPP_STARTUP_FUNCTION(installIOSInitialLifecycle)
