// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "NativeMetrics.h"
#include <QCoreApplication>
#include <QGuiApplication>
#include <QTimer>

namespace {
void installIOSNativeMetrics() {
    // Q_COREAPP_STARTUP_FUNCTION runs during the base application constructor;
    // defer until the concrete GUI application and its event loop exist.
    auto* app = QCoreApplication::instance();
    QTimer::singleShot(0, app, [app] {
        auto* timer = new QTimer(app);
        timer->setInterval(30000);
        timer->setTimerType(Qt::VeryCoarseTimer);
        QObject::connect(timer, &QTimer::timeout, app, [] {
            if (QGuiApplication::applicationState() == Qt::ApplicationActive) {
                overte::ios::logNativeMetrics(overte::ios::sampleNativeMetrics());
            }
        });
        timer->start();
    });
}
}
Q_COREAPP_STARTUP_FUNCTION(installIOSNativeMetrics)
