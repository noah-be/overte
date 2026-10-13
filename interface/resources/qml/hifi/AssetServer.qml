// Copyright 2017 High Fidelity, Inc.
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import "../windows" as Windows
import "dialogs"
Windows.ScrollingWindow {
    id: root
    objectName: "AssetServer"
    title: "Asset Browser"
    resizable: true
    destroyOnHidden: true
    implicitWidth: 700
    implicitHeight: 760
    minSize: Qt.vector2d(360, 500)
    keyboardOverride: true
    contentFlickableInteractive: true
    TabletAssetServer { width: parent.width; height: Math.max(600, root.pane.scrollHeight) }
}
