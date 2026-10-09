// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QQmlComponent>
#include <QQmlEngine>

inline void phoneInitializeQuickTypes() {
#if defined(ANDROID_APP_PHONE_INTERFACE) && QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    // Qt 5 caches a missing attached-property lookup on first use. Register
    // Qt Quick before any render-control window can query accessibility.
    static const bool ready = [] {
        QQmlEngine bootstrap;
        QQmlComponent component(&bootstrap);
        component.setData("import QtQuick 2.7\nQtObject {}", QUrl());
        if (!component.isReady()) { qFatal("Cannot initialize the phone Qt Quick types"); }
        return true;
    }();
    Q_UNUSED(ready);
#endif
}
