//
//  WindowRoot.qml
//
//  Created by Anthony Thibault on 14 Feb 2017
//  Copyright 2017 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
//  This qml is used when tablet content is shown on the 2d overlay ui
//  TODO: FIXME: this is practically identical to TabletRoot.qml

import "../../windows" as Windows
import QtQuick 2.0
import Hifi 1.0
import TabletScriptingInterface 1.0

import Qt.labs.settings 1.0
import controlsUit 1.0 as HifiControls

Windows.ScrollingWindow {
    id: tabletRoot
    objectName: "tabletRoot"
    property string username: "Unknown user"
    signal screenChanged(var type, var url);

    property var rootMenu;
    property string subMenu: ""
    property var tabletProxy: Tablet.getTablet("com.highfidelity.interface.tablet.system")
    property var semanticSourceHistory: []
    property string semanticBackTarget: ""
    HifiControls.TouchUiProfile { id: touchUiProfile }
    property bool screenSpaceMode: false
    property real screenSpaceContentScale: touchUiProfile.screenSpaceContentScale
    property int screenSpaceSafeInsetLeft: touchUiProfile.safeInsetLeft
    property int screenSpaceSafeInsetTop: touchUiProfile.safeInsetTop
    property int screenSpaceSafeInsetRight: touchUiProfile.safeInsetRight
    property int screenSpaceSafeInsetBottom: touchUiProfile.safeInsetBottom
    property int screenSpaceImeInsetBottom: touchUiProfile.imeInsetBottom
    property bool screenSpaceKeyboardVisible: touchUiProfile.keyboardVisible
    property int screenSpaceSurfaceWidth: touchUiProfile.surfaceWidth
    property int screenSpaceSurfaceHeight: touchUiProfile.surfaceHeight
    property real screenSpaceDensity: touchUiProfile.density
    property real screenSpaceFontScale: touchUiProfile.fontScale

    shown: false
    resizable: false
    closable: !screenSpaceMode
    pinnable: !screenSpaceMode
    alwaysOnTop: screenSpaceMode
    contentFlickableInteractive: !touchUiProfile.directTouch || !screenSpaceMode
    TabletSurfaceGeometry { id: surfaceGeometry; profile: touchUiProfile }

    function setScreenSpaceMode(value) {
        screenSpaceMode = value
        frame.visible = !value
        if (value) {
            // Windows.Window repositions newly visible framed windows so their
            // hidden title decoration remains on-screen. Reassert the real
            // screen origin after that visibility pass for the frameless
            // Android presenter.
            Qt.callLater(alignScreenSpaceWindow)
        }
    }

    function alignScreenSpaceWindow() {
        if (screenSpaceMode) {
            x = surfaceGeometry.x
            y = surfaceGeometry.y
            if (surfaceGeometry.valid) {
                width = surfaceGeometry.width
                height = surfaceGeometry.height
            }
        }
    }

    onVisibleChanged: if (visible && screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)
    Connections {
        target: surfaceGeometry
        function onXChanged() { if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow) }
        function onYChanged() { if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow) }
        function onWidthChanged() { if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow) }
        function onHeightChanged() { if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow) }
    }

    Settings {
        id: settings
        category: "WindowRoot.Windows"
        property real width: 480
        property real height: 706
    }

    onResizableChanged: {
        // TabletProxy uses setResizable(false) when loading most tablet apps.
        // In Android screen-space mode that must not restore the historical
        // 480x706 desktop window over the full physical surface.
        if (screenSpaceMode) {
            return
        }
        if (!resizable) {
            // restore default size
            settings.width = tabletRoot.width
            settings.height = tabletRoot.height
            tabletRoot.width = 480
            tabletRoot.height = 706
        } else {
            tabletRoot.width = settings.width
            tabletRoot.height = settings.height
        }
    }

    signal showDesktop();

    function setResizable(value) {
        tabletRoot.resizable = value;
    }

    function setMenuProperties(rootMenu, subMenu) {
        tabletRoot.rootMenu = rootMenu;
        tabletRoot.subMenu = subMenu;
    }

    function loadSource(url) {
        var restoringPrevious = semanticBackTarget !== "" && semanticBackTarget === url
        semanticBackTarget = ""
        if (url === "hifi/tablet/TabletHome.qml") {
            semanticSourceHistory = []
        } else if (!restoringPrevious && loader.source !== "" && loader.source !== url) {
            semanticSourceHistory = semanticSourceHistory.concat([loader.source])
        }
        loader.load(url)
    }

    function returnToPreviousSemanticScreen() {
        if (semanticBackTarget !== "") { return true }
        if (loader.item && typeof loader.item.handleTabletBack === "function"
                && loader.item.handleTabletBack() === true) {
            return true
        }
        if (loader.source === "hifi/tablet/TabletHome.qml") {
            tabletProxy.hideAndroidTablet()
            return true
        }
        if (semanticSourceHistory.length === 0) {
            tabletProxy.gotoHomeScreen()
            return true
        }
        var previous = semanticSourceHistory[semanticSourceHistory.length - 1]
        semanticSourceHistory = semanticSourceHistory.slice(0, -1)
        semanticBackTarget = previous
        // Use the proxy so its current source/state and screenChanged clients
        // agree with the page shown by the loader after Back.
        if (previous === "hifi/tablet/TabletHome.qml") {
            tabletProxy.gotoHomeScreen()
        } else {
            tabletProxy.loadQMLSource(previous)
        }
        return true
    }

    function loadWebContent(source, url, injectJavaScriptUrl) {
        loader.load(source, function() {
            loader.item.scriptURL = injectJavaScriptUrl;
            loader.item.url = url;
            if (loader.item.hasOwnProperty("closeButtonVisible")) {
                loader.item.closeButtonVisible = false;
            }
            
            screenChanged("Web", url);
        });
    }

    function loadWebBase(url, injectJavaScriptUrl) {
        loadWebContent("hifi/tablet/TabletWebView.qml", url, injectJavaScriptUrl);
    }

    function loadTabletWebBase(url, injectJavaScriptUrl) {
        loadWebContent("hifi/tablet/BlocksWebView.qml", url, injectJavaScriptUrl);
    }

    // used to send a message from qml to interface script.
    signal sendToScript(var message);

    // used to receive messages from interface script
    function fromScript(message) {
        if (loader.item !== null) {
            if (loader.item.hasOwnProperty("fromScript")) {
                loader.item.fromScript(message);
            }
        }
    }

    SoundEffect {
        id: buttonClickSound
        volume: 0.1
        source: "../../../sounds/Gamemaster-Audio-button-click.wav"
    }

    footer: TabletNavigation {
        width: parent.width
        visible: touchUiProfile.directTouch && tabletRoot.screenSpaceMode
            && loader.source !== "" && loader.source !== "hifi/tablet/TabletHome.qml"
        contentScale: tabletRoot.screenSpaceContentScale
        backVisible: !loader.item || !loader.item.hasOwnProperty("currentPage")
        onBackRequested: tabletRoot.returnToPreviousSemanticScreen()
        onHomeRequested: tabletProxy.gotoHomeScreen()
        onCloseRequested: tabletProxy.hideAndroidTablet()
    }

    function playButtonClickSound() {
        // Because of the asynchronous nature of initalization, it is possible for this function to be
        // called before the C++ has set the globalPosition context variable.
        if (typeof globalPosition !== 'undefined') {
            buttonClickSound.play(globalPosition);
        }
    }

    function setUsername(newUsername) {
        username = newUsername;
    }

    // Hook up callback for clara.io download from the marketplace.
    Connections {
        id: eventBridgeConnection
        target: eventBridge
        function onWebEventReceived(message) {
            if (typeof message === "string" && message.slice(0, 17) === "CLARA.IO DOWNLOAD") {
                ApplicationInterface.addAssetToWorldFromURL(message.slice(18));
            }
        }
    }

    TabletPageLoader {
        id: loader
        rootMenu: tabletRoot.rootMenu
        subMenu: tabletRoot.subMenu
        sharedTouchNavigation: tabletRoot.screenSpaceMode && touchUiProfile.directTouch
        onScreenChanged: function(type, url) { tabletRoot.screenChanged(type, url) }
        onSendToScript: function(message) { tabletRoot.sendToScript(message) }
        onHomeRequested: tabletProxy.gotoHomeScreen()
        readonly property real contentScale: tabletRoot.screenSpaceMode
            ? tabletRoot.screenSpaceContentScale : 1.0
        transformOrigin: Item.TopLeft
        scale: contentScale
        height: pane.scrollHeight / contentScale
        width: pane.contentWidth / contentScale
        // ScrollingWindow reparents its content into the Flickable.
        onParentChanged: {
            if (parent) {
                anchors.left = Qt.binding(function() { return parent.left })
                anchors.top = Qt.binding(function() { return parent.top })
            } else {
                anchors.left = undefined
                anchors.top = undefined
            }
        }
    }


    implicitWidth: 480
    implicitHeight: 706
}
