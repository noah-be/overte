// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../src/RedactingDiagnostics.h"
#include <QByteArray>
#include <QDebug>
#include <QString>

namespace {
void safeIOSQtMessage(QtMsgType, const QMessageLogContext&, const QString& message) {
    // Discard the context (file/function/category/line) entirely. Application
    // later installs the General-owned PX-16 sink, preserving this boundary.
    auto bytes = message.toUtf8();
    overte::ios::logRedactedDiagnostic(bytes.constData(), static_cast<std::size_t>(bytes.size()));
    bytes.fill('\0');
}
// The actual main.cpp emits diagnostics before constructing QCoreApplication.
// Install in this directly linked object before main, rather than after startup.
struct InstallSafeIOSQtLogging {
    InstallSafeIOSQtLogging() { qInstallMessageHandler(safeIOSQtMessage); }
};
InstallSafeIOSQtLogging installSafeIOSQtLogging;
}
