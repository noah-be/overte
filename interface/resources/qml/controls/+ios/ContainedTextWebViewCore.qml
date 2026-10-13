// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: flick
    property alias url: bridge.url
    readonly property bool canGoBack: false
    property alias webViewCore: bridge
    property bool useBackground: false
    property string userAgent: ""
    property string userScriptUrl: ""
    property string urlTag: "noDownload=false"
    property bool interactive: true
    property bool blurOnCtrlShift: true
    property double nativeTicket: 0
    property bool requestRejected: false
    signal newViewRequestedCallback(var request)
    signal loadingChangedCallback(var loadRequest)

    // URL assignment never creates a view, performs network I/O or injects JS.
    // Only this explicit action requests the native origin-confirmation UI.
    function openNative() {
        stop();
        if (!visible || !enabled || !interactive || userScriptUrl.length > 0 ||
                typeof ApplicationInterface === "undefined") {
            requestRejected = true;
            return false;
        }
        nativeTicket = ApplicationInterface.openContainedNativeWeb(bridge.url.toString());
        requestRejected = nativeTicket === 0;
        return !requestRejected;
    }
    function stop() {
        if (nativeTicket !== 0 && typeof ApplicationInterface !== "undefined") {
            ApplicationInterface.closeContainedNativeWeb(nativeTicket);
        }
        nativeTicket = 0;
    }
    function unfocus() { openButton.focus = false; }
    function stopUnfocus() { stop(); unfocus(); }
    onVisibleChanged: { if (!visible) stopUnfocus(); }
    onEnabledChanged: { if (!enabled) stopUnfocus(); }
    onUserScriptUrlChanged: stop()
    Component.onDestruction: stop()

    Item {
        id: bridge
        property url url: ""
        readonly property bool canGoBack: false
        readonly property bool canGoForward: false
        readonly property bool loading: false
        onUrlChanged: { flick.stop(); flick.requestRejected = false; }
        // Native controls own navigation. No simulated WebEngine history,
        // script bridge, cache bypass or loading-success callback is provided.
        function goBack() { return false; }
        function goForward() { return false; }
        function reload() { return false; }
        function reloadAndBypassCache() { return false; }
        function runJavaScript(code, callback) { flick.requestRejected = true; return false; }
        function setActiveFocusOnPress(value) { if (!value) flick.unfocus(); }
        function setEnabled(value) { flick.enabled = value; }
        function forceActiveFocus() { if (openButton.enabled && flick.visible) openButton.forceActiveFocus(); }
    }

    Column {
        anchors.centerIn: parent
        width: Math.max(0, Math.min(parent.width - 32, 420))
        spacing: 12
        Text {
            width: parent.width
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            color: "white"
            text: flick.requestRejected
                  ? qsTr("This web request is unavailable or not allowed.")
                  : qsTr("Inline web content is unavailable. Open a native view to review this link.")
            Accessible.name: text
        }
        Button {
            id: openButton
            anchors.horizontalCenter: parent.horizontalCenter
            text: qsTr("Open native web view")
            enabled: flick.enabled && flick.interactive && bridge.url.toString().length > 0 && flick.userScriptUrl.length === 0
            onClicked: flick.openNative()
        }
    }
}
