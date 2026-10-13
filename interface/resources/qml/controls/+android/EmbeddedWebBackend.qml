// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import Overte.Android 1.0

Item {
    id: root
    property string url: ""
    property string scriptUrl: ""
    property string userAgent: ""
    property bool useBackground: true
    property string eventBridgeJavaScript: ""
    property string sourceIdentity: ""
    property string surface: "world-entity"
    readonly property string currentUrl: nativeView.currentUrl
    readonly property bool loading: nativeView.loading
    readonly property bool canGoBack: nativeView.canGoBack
    readonly property bool canGoForward: nativeView.canGoForward
    readonly property string error: nativeView.error
    readonly property bool bridgeAvailable: nativeView.bridgeAvailable
    signal webEventReceived(var message)
    signal loadingChangedWithStatus(var change)
    function emitScriptEvent(message) { return nativeView.emitScriptEvent(message); }
    function runJavaScript(source, callback) { return nativeView.runJavaScript(source, callback); }
    function openNative() { nativeView.openNative(); }
    function goBack() { nativeView.goBack(); }
    function goForward() { nativeView.goForward(); }
    function reload() { nativeView.reload(); }
    function reloadAndBypassCache() { nativeView.reloadAndBypassCache(); }
    function stop() { nativeView.stop(); }
    function unfocus() { nativeView.unfocus(); }
    NativeWebView {
        id: nativeView
        anchors.fill: parent
        url: root.url
        scriptUrl: root.scriptUrl
        userAgent: root.userAgent
        useBackground: root.useBackground
        eventBridgeJavaScript: root.eventBridgeJavaScript
        sourceIdentity: root.sourceIdentity
        surface: root.surface === "tablet" ? NativeWebView.Tablet : NativeWebView.WorldEntity
        presentation: root.surface === "tablet" ? NativeWebView.NativeOverlay : NativeWebView.Texture
        onWebEventReceived: root.webEventReceived(message)
        onStateChanged: root.loadingChangedWithStatus({ status: loading ? 0 : (error.length ? 3 : 2), errorString: error })
    }
}
