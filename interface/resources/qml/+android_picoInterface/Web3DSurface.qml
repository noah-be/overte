// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import controlsUit 1.0 as Controls

Item {
    id: root
    anchors.fill: parent
    property string url: ""
    property string scriptUrl: ""
    property bool useBackground: true
    property string userAgent: ""
    readonly property var item: loader.item
    readonly property bool webViewLoaded: !/\.qml(?:[?#].*)?$/.test(url)
    property bool keyboardEnabled: true
    property bool keyboardRaised: false
    property bool punctuationMode: false
    property bool passwordField: false
    property bool _ready: false
    property string _source: ""
    signal sendToScript(var message)

    function fromScript(message) {
        if (loader.item && loader.item.fromScript) { loader.item.fromScript(message); }
    }
    function _set(name, value) {
        if (loader.item && loader.item[name] !== value) { loader.item[name] = value; }
    }
    function _load() {
        if (!_ready) { return; }
        keyboardRaised = false;
        punctuationMode = false;
        passwordField = false;
        // Keep Pico's working inline-HTML renderer. The common source grant
        // intentionally excludes data documents from privileged WebChannel use.
        // A direct physical load and Qt's logical selector entry have different
        // bases. Resolve the sibling shared component from either entry.
        var base = Qt.resolvedUrl(".").toString();
        var commonBase = base.replace(/\+android_picoInterface\/$/, "");
        var source = /^data:text\/html(?:[;,]|$)/i.test(url)
            ? base + "PicoLegacyWebSurface.qml"
            : commonBase + "+android_interface/Web3DSurface.qml";
        if (_source === source) {
            _set("url", url);
            return;
        }
        if (loader.item) {
            // Blank the legacy page before releasing its native handle/audio.
            loader.item.url = "about:blank";
        }
        _source = source;
        loader.setSource(source, { url: url, scriptUrl: scriptUrl,
                                  useBackground: useBackground, userAgent: userAgent });
    }
    onUrlChanged: _load()
    onScriptUrlChanged: _set("scriptUrl", scriptUrl)
    onUseBackgroundChanged: _set("useBackground", useBackground)
    onUserAgentChanged: _set("userAgent", userAgent)
    onKeyboardRaisedChanged: {
        if (!keyboardRaised && loader.item && loader.item.item && loader.item.item.unfocus) {
            loader.item.item.unfocus();
        }
    }
    Component.onCompleted: { _ready = true; _load(); }
    Component.onDestruction: keyboardRaised = false
    Loader {
        id: loader
        width: parent.width
        height: keyboardEnabled && keyboardRaised ? Math.max(0, parent.height - keyboard.height) : parent.height
    }
    Connections {
        target: loader.item
        ignoreUnknownSignals: true
        function onSendToScript(message) { root.sendToScript(message); }
        function onEditorStateChanged() {
            var editor = loader.item && loader.item.item;
            root.punctuationMode = editor ? editor.editorNumeric : false;
            root.passwordField = editor ? editor.editorPassword : false;
            root.keyboardRaised = root.keyboardEnabled && editor && editor.editorFocused;
        }
    }
    Controls.Keyboard {
        id: keyboard
        raised: root.keyboardEnabled && root.keyboardRaised
        numeric: root.punctuationMode
        password: root.passwordField
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
    }
}
