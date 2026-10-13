// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Controls 2.3

Item {
    id: root
    objectName: "stack"
    signal sendToScript(var message)

    Loader {
        id: page
        anchors.fill: parent
        sourceComponent: Qt.platform.os === "android" || Qt.platform.os === "ios"
            ? nativePage : desktopPage
    }
    Component {
        id: nativePage
        StackView {
            id: nativeStack
            initialItem: NativeCreate { onSendToScript: root.sendToScript(message) }
            function fromScript(message) {
                if (currentItem && currentItem.fromScript) { currentItem.fromScript(message) }
            }
            function pushSource(path) {
                var dialog = push(path, {}, StackView.Immediate)
                if (dialog && dialog.sendToScript) { dialog.sendToScript.connect(root.sendToScript) }
            }
            function popSource() { pop(StackView.Immediate) }
        }
    }
    Component {
        id: desktopPage
        EditDesktop { onSendToScript: root.sendToScript(message) }
    }

    function fromScript(message) {
        if (page.item && page.item.fromScript) { page.item.fromScript(message) }
    }
    function pushSource(path) {
        if (page.item && page.item.pushSource) { page.item.pushSource(path) }
    }
    function popSource() {
        if (page.item && page.item.popSource) { page.item.popSource() }
    }
}
