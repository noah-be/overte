// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QCoreApplication>
#include <QGuiApplication>

inline QCoreApplication* phoneApplication() {
    // main() first creates a temporary parser app. Its queued work is deleted
    // before the real client exists; Android must retain and retry that work.
    return qobject_cast<QGuiApplication*>(QCoreApplication::instance());
}
