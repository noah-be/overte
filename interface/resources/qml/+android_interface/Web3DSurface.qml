//
//  Web3DSurface.qml
//
//  Created by Gabriel Calero & Cristian Duarte on Jun 22, 2018
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.5

Item {
    id: root
    anchors.fill: parent
    property string url: ""
    property string scriptUrl: ""
    property bool useBackground: true
    property string userAgent: ""
    property bool _ready: false

    onUrlChanged: {
        if (_ready) { load(root.url, root.scriptUrl, root.useBackground, root.userAgent); }
    }

    onScriptUrlChanged: {
        if (!_ready) { return; }
        if (loader.item) {
            if (root.webViewLoaded) {
                loader.item.scriptUrl = root.scriptUrl;
            }
        } else {
            load(root.url, root.scriptUrl, root.useBackground, root.userAgent);
        }
    }

    onUseBackgroundChanged: {
        if (!_ready) { return; }
        if (loader.item) {
            if (root.webViewLoaded) {
                loader.item.useBackground = root.useBackground;
            }
        } else {
            load(root.url, root.scriptUrl, root.useBackground, root.userAgent);
        }
    }

    onUserAgentChanged: {
        if (!_ready) { return; }
        if (loader.item) {
            if (root.webViewLoaded) {
                loader.item.userAgent = root.userAgent;
            }
        } else {
            load(root.url, root.scriptUrl, root.useBackground, root.userAgent);
        }
    }

    readonly property var item: loader.item
    property bool webViewLoaded: false

    // Handle message traffic from the script that launched us to the loaded QML
    function fromScript(message) {
        if (loader.item && loader.item.fromScript) {
            loader.item.fromScript(message);
        }
    }

    Loader {
        id: loader
        anchors.fill: parent
    }

    Connections {
        target: loader.item
        ignoreUnknownSignals: true
        function onSendToScript(message) { root.sendToScript(message); }
    }

    function load(url, scriptUrl, useBackground, userAgent) {
        // Release the previous native page before replacing its source grant.
        if (loader.item && root.webViewLoaded) {
            if (loader.item.stop) { loader.item.stop(); }
        }

        if (/\.qml(?:[?#].*)?$/.test(url)) {
            root.webViewLoaded = false;
            loader.setSource(url);
        } else {
            root.webViewLoaded = true;
            loader.setSource("./Web3DSurfaceAndroid.qml", {
                url: url,
                scriptUrl: scriptUrl,
                useBackground: useBackground,
                userAgent: userAgent
            });
        }
    }

    Component.onCompleted: {
        _ready = true;
        load(root.url, root.scriptUrl, root.useBackground, root.userAgent);
    }

    signal sendToScript(var message);
}
