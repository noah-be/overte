// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Controls 2.2 as QuickControls

Item {
    id: flick
    property alias url: webView.url
    property alias canGoBack: webView.canGoBack
    property alias canGoForward: webView.canGoForward
    property alias webViewCore: webView
    property alias useBackground: webView.useBackground
    property alias userAgent: webView.userAgent
    property alias userScriptUrl: webView.scriptUrl
    property string urlTag: "noDownload=false"
    property bool interactive: true
    property bool blurOnCtrlShift: true
    signal newViewRequestedCallback(var request)
    signal loadingChangedCallback(var loadRequest)
    signal nativeClosed()
    function stop() { webView.stop(); }
    function unfocus() { webView.unfocus(); }
    // Tablet keyboard transitions must preserve the current browser document.
    function stopUnfocus() { unfocus(); }
    function openNative() { return webView.openNative(); }
    function onLoadingChanged(loadRequest) {}
    Row {
        id: navigation
        width: parent.width
        height: 48
        spacing: 4
        QuickControls.Button {
            objectName: "EmbeddedWebBack"
            width: (navigation.width - 12) / 4
            height: navigation.height
            text: qsTr("Back")
            enabled: flick.interactive && webView.canGoBack
            focusPolicy: Qt.NoFocus
            onClicked: webView.goBack()
        }
        QuickControls.Button {
            objectName: "EmbeddedWebForward"
            width: (navigation.width - 12) / 4
            height: navigation.height
            text: qsTr("Forward")
            enabled: flick.interactive && webView.canGoForward
            focusPolicy: Qt.NoFocus
            onClicked: webView.goForward()
        }
        QuickControls.Button {
            objectName: "EmbeddedWebReload"
            width: (navigation.width - 12) / 4
            height: navigation.height
            text: qsTr("Reload")
            enabled: flick.interactive && webView.url.length > 0
            focusPolicy: Qt.NoFocus
            onClicked: webView.reload()
        }
        QuickControls.Button {
            objectName: "EmbeddedWebClose"
            width: (navigation.width - 12) / 4
            height: navigation.height
            text: qsTr("Close")
            focusPolicy: Qt.NoFocus
            onClicked: { flick.stop(); flick.nativeClosed(); }
        }
    }
    EmbeddedWebView {
        id: webView
        anchors { left: parent.left; right: parent.right; top: navigation.bottom; bottom: parent.bottom }
        enabled: flick.enabled && flick.interactive
        surface: "tablet"
        onLoadingChangedWithStatus: {
            flick.onLoadingChanged(change);
            flick.loadingChangedCallback(change);
        }
        onNativeClosed: flick.nativeClosed()
    }
}
