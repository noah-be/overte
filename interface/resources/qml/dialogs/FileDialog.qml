// Copyright 2015 High Fidelity, Inc.
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import "../windows" as Windows
Windows.ModalWindow {
    id: root
    objectName: "FileDialog"
    colorScheme: 0
    title: browser.caption
    property int titleWidth: 0
    resizable: true
    implicitWidth: 600
    implicitHeight: 680
    minSize: Qt.vector2d(360, 400)
    keyboardOverride: true
    contentFlickableInteractive: true
    property alias caption: browser.caption
    property alias dir: browser.dir
    property alias filter: browser.filter
    property alias options: browser.options
    property alias selectDirectory: browser.selectDirectory
    property alias showHidden: browser.showHidden
    property alias bundleMode: browser.bundleMode
    property alias primaryFilter: browser.primaryFilter
    property alias multiSelect: browser.multiSelect
    property alias saveDialog: browser.saveDialog
    property alias helper: browser.helper
    property alias model: browser.model
    signal selectedFile(var file)
    signal canceled()
    NativeFileBrowser {
        id: browser
        destroyOnCompletion: false
        anchors.fill: undefined
        width: parent.width
        height: Math.max(640, root.pane.scrollHeight)
        onSelectedFile: function(file) { root.selectedFile(file); Qt.callLater(function() { root.destroy(); }); }
        onCanceled: { root.canceled(); Qt.callLater(function() { root.destroy(); }); }
    }
}
