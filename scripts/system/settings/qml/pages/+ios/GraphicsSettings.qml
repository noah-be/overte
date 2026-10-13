// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.15

Loader {
    anchors.fill: parent
    // Selected types can be addressed through their original or physical URL.
    source: Qt.resolvedUrl("GraphicsSettingsBase.qml").toString()
              .replace(/\/\+ios\/GraphicsSettingsBase.qml$/, "/GraphicsSettingsBase.qml")
}
