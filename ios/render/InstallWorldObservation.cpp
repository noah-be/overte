// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "WorldObservation.h"

// No exporter in ordinary applications. The already supported explicit world
// evidence launch flag additionally opts this E2E build into bounded recording.
#if defined(Q_OS_IOS) && (defined(OVERTE_IOS_E2E_TEST_BUILD) || defined(OVERTE_IOS_WORLD_OBSERVATION_BUILD))
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QGuiApplication>
#include <QStandardPaths>
#include <QTimer>
#include <memory>

namespace {
void installWorldObservation() {
    auto* app = QCoreApplication::instance();
    QTimer::singleShot(0, app, [app] {
        auto* gui = qobject_cast<QGuiApplication*>(app);
        if (!gui || !app->arguments().contains("--ios-world-evidence")) { return; }
        const auto directory = QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation);
        auto elapsed = std::make_shared<QElapsedTimer>();
        auto finished = std::make_shared<bool>(false);
        elapsed->start();
        auto* timer = new QTimer(app);
        timer->setInterval(1000);
        const auto publish = [directory, elapsed, finished, timer] {
            if (*finished) { return; }
            auto sample = overte::ios::worldObservation(
                QGuiApplication::applicationState() == Qt::ApplicationActive);
            sample["elapsedMs"] = QString::number(elapsed->elapsed());
            // A fixed ten-minute acquisition, one atomically replaced file.
            // Expiry is represented explicitly, never a stale ready snapshot.
            const bool expired = elapsed->elapsed() >= 600000;
            sample["expired"] = expired;
            if (!overte::ios::writeWorldObservation(directory, sample) || expired) {
                *finished = true;
                timer->stop();
            }
        };
        QObject::connect(timer, &QTimer::timeout, app, publish);
        QObject::connect(gui, &QGuiApplication::applicationStateChanged, timer,
            [publish](Qt::ApplicationState) { publish(); });
        timer->start();
        publish();
    });
}
}
Q_COREAPP_STARTUP_FUNCTION(installWorldObservation)
#endif
