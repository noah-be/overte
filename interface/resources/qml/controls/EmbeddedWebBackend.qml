// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7

// OS file selectors replace this type with the corresponding native backend.
Item {
    property string url: ""
    property string scriptUrl: ""
    property string userAgent: ""
    property bool useBackground: true
    property string eventBridgeJavaScript: ""
    property string sourceIdentity: ""
    property string surface: "world-entity"
    readonly property string currentUrl: url
    readonly property bool loading: false
    readonly property bool canGoBack: false
    readonly property bool canGoForward: false
    readonly property string error: qsTr("Embedded web content is unavailable on this client.")
    readonly property bool bridgeAvailable: false
    signal webEventReceived(var message)
    signal nativeClosed()
    function emitScriptEvent(message) { return false; }
    function runJavaScript(source, callback) { return false; }
    function openNative() { return false; }
    function goBack() { return false; }
    function goForward() { return false; }
    function reload() { return false; }
    function reloadAndBypassCache() { return false; }
    function stop() {}
    function unfocus() {}
    Text {
        anchors.centerIn: parent
        width: Math.max(0, parent.width - 32)
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        color: "white"
        text: parent.error
    }
}
