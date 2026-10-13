// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7

FocusScope {
    id: root
    property string url: ""
    property string scriptUrl: ""
    property string userAgent: ""
    property bool useBackground: true
    property string surface: "world-entity"
    property string sourceIdentity: "web-surface-" + Date.now() + "-" + Math.random()
    property string eventBridgeJavaScript: typeof eventBridgeJavaScriptToInject !== "undefined"
                                          ? eventBridgeJavaScriptToInject : ""
    readonly property var backend: loader.item
    readonly property string currentUrl: backend && typeof backend.currentUrl !== "undefined"
                                         ? backend.currentUrl.toString() : url
    readonly property bool loading: backend ? backend.loading : false
    readonly property bool canGoBack: backend ? backend.canGoBack : false
    readonly property bool canGoForward: backend ? backend.canGoForward : false
    readonly property string error: backend ? backend.error : ""
    readonly property bool bridgeAvailable: backend ? backend.bridgeAvailable : false
    property bool _ready: false
    signal webEventReceived(var message)
    signal loadingChangedWithStatus(var change)
    signal nativeClosed()

    function _set(name, value) {
        if (backend && backend[name] !== value) { backend[name] = value; }
    }
    function _load() {
        if (!_ready || !url.length) { return; }
        if (backend) { _set("url", url); return; }
        // Configure the native source grant before the first navigation.
        loader.setSource("EmbeddedWebBackend.qml", {
            sourceIdentity: sourceIdentity, surface: surface,
            eventBridgeJavaScript: eventBridgeJavaScript,
            scriptUrl: scriptUrl, userAgent: userAgent,
            useBackground: useBackground, url: url, focus: true
        });
    }
    function _reportLoading() {
        if (!backend || !url.length) { return; }
        loadingChangedWithStatus({ status: loading ? 0 : (error.length ? 3 : 2),
                                   errorString: error });
    }
    function emitScriptEvent(message) {
        if (backend && root.visible && root.enabled) { backend.emitScriptEvent(message); }
    }
    function fromScript(message) { emitScriptEvent(message); }
    function runJavaScript(source, callback) {
        return backend ? backend.runJavaScript(source, callback) : false;
    }
    function openNative() { return backend ? backend.openNative() : false; }
    function goBack() { return backend ? backend.goBack() : false; }
    function goForward() { return backend ? backend.goForward() : false; }
    function reload() { return backend ? backend.reload() : false; }
    function reloadAndBypassCache() { return backend ? backend.reloadAndBypassCache() : false; }
    function stop() { if (backend) { backend.stop(); } }
    function unfocus() { if (backend) { backend.unfocus(); } }
    function setActiveFocusOnPress(value) { if (!value) { unfocus(); } }
    function setEnabled(value) { root.enabled = value; }
    onUrlChanged: _load()
    onScriptUrlChanged: _set("scriptUrl", scriptUrl)
    onUserAgentChanged: _set("userAgent", userAgent)
    onUseBackgroundChanged: _set("useBackground", useBackground)
    onSurfaceChanged: _set("surface", surface)
    onSourceIdentityChanged: _set("sourceIdentity", sourceIdentity)
    onEventBridgeJavaScriptChanged: _set("eventBridgeJavaScript", eventBridgeJavaScript)
    onLoadingChanged: _reportLoading()
    onErrorChanged: { if (!loading) { _reportLoading(); } }
    onEnabledChanged: { if (!enabled) { unfocus(); } }
    Component.onCompleted: { _ready = true; _load(); }
    Component.onDestruction: stop()
    Loader {
        id: loader
        anchors.fill: parent
        active: root.url.length > 0
        focus: true
    }
    Rectangle {
        anchors.fill: parent
        visible: root.error.length > 0
        color: "#262626"
        Text {
            anchors.centerIn: parent
            width: Math.max(0, parent.width - 32)
            text: root.error
            color: "white"
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            Accessible.name: text
        }
    }
    Connections {
        target: loader.item
        ignoreUnknownSignals: true
        function onWebEventReceived(message) {
            // The native endpoint validates source/document/frame authority.
            // The real WebChannel bootstrap may flush events before idle.
            if (root.visible && root.enabled) {
                root.webEventReceived(message);
                if (typeof eventBridge !== "undefined") { eventBridge.emitWebEvent(message); }
            }
        }
        function onNativeClosed() { root.nativeClosed(); }
    }
    Connections {
        target: typeof eventBridge !== "undefined" ? eventBridge : null
        ignoreUnknownSignals: true
        function onScriptEventReceived(message) {
            if (root.visible && root.enabled) { root.emitScriptEvent(message); }
        }
    }
}
