// Copyright 2016 High Fidelity, Inc.
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import "../../windows" as Windows
Windows.ScrollingWindow {
    id: root
    objectName: "RunningScripts"
    title: "Running Scripts"
    resizable: true
    destroyOnHidden: false
    implicitWidth: 600
    implicitHeight: 700
    minSize: Qt.vector2d(360, 400)
    keyboardOverride: true
    contentFlickableInteractive: true
    TabletRunningScripts { width: parent.width; height: Math.max(600, root.pane.scrollHeight) }
}
