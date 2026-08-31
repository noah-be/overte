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
    contentFlickableInteractive: Qt.platform.os !== "ios" || !screenSpaceMode

    function setScreenSpaceMode(value) {
        screenSpaceMode = value
        frame.visible = !value
        if (value) {
            // Windows.Window repositions newly visible framed windows so their
            // hidden title decoration remains on-screen. Reassert the local
            // safe-content origin after that visibility pass for the
            // frameless mobile presenter.
            Qt.callLater(alignScreenSpaceWindow)
        }
    }

    function alignScreenSpaceWindow() {
        if (screenSpaceMode) {
            if (Qt.platform.os === "ios") {
                // The iOS offscreen surface already represents UIKit's safe
                // content rectangle, so its children use a local origin.
                x = 0
                y = 0
            } else {
                // Android's surface covers the full display and still needs
                // explicit rounded-corner and status-bar margins.
                x = screenSpaceSafeInsetLeft
                y = screenSpaceSafeInsetTop
            }
            width = Math.max(1, screenSpaceSurfaceWidth
                - screenSpaceSafeInsetLeft - screenSpaceSafeInsetRight)
            height = Math.max(1, screenSpaceSurfaceHeight
                - screenSpaceSafeInsetTop
                - Math.max(screenSpaceSafeInsetBottom, screenSpaceImeInsetBottom))
        }
    }

    onVisibleChanged: if (visible && screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)
    onScreenSpaceSafeInsetLeftChanged: if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)
    onScreenSpaceSafeInsetTopChanged: if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)
    onScreenSpaceSafeInsetRightChanged: if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)
    onScreenSpaceSafeInsetBottomChanged: if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)
    onScreenSpaceImeInsetBottomChanged: if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)
    onScreenSpaceSurfaceWidthChanged: if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)
    onScreenSpaceSurfaceHeightChanged: if (screenSpaceMode) Qt.callLater(alignScreenSpaceWindow)

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
        if (url === "hifi/tablet/TabletHome.qml") {
            semanticSourceHistory = []
        } else if (loader.source !== "" && loader.source !== url) {
            semanticSourceHistory = semanticSourceHistory.concat([loader.source])
        }
        loader.load(url)
    }

    function returnToPreviousSemanticScreen() {
        if (semanticSourceHistory.length === 0) {
            tabletProxy.gotoHomeScreen()
            return
        }
        var previous = semanticSourceHistory[semanticSourceHistory.length - 1]
        semanticSourceHistory = semanticSourceHistory.slice(0, -1)
        loader.load(previous)
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

    readonly property string semanticScreenId: {
        if (!loader.item) {
            return ""
        }
        if (loader.item.hasOwnProperty("semanticScreenId")) {
            return loader.item.semanticScreenId
        }
        return loader.item.objectName || ""
    }
    readonly property bool semanticSettingsScreen:
        semanticScreenId.indexOf("settings.") === 0
    readonly property bool semanticBackUsesSettingsHeader:
        loader.source.indexOf("scripts/system/settings/Settings.qml") !== -1

    // Flat-touch iOS keeps navigation visible on every Settings screen. These
    // are production controls; the E2E-only native bridge merely projects the
    // same frames and Accessible press actions into XCUITest.
    Row {
        id: semanticNavigation
        z: 100000
        visible: Qt.platform.os === "ios" && tabletRoot.screenSpaceMode
            && tabletRoot.semanticSettingsScreen
        spacing: 12
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 8
        height: 56
        property real buttonWidth: Math.max(80, Math.min(112,
            (tabletRoot.width - 2 * spacing - 16) / 3))

        Rectangle {
            id: semanticBack
            objectName: "nav.back"
            visible: tabletRoot.semanticScreenId !== "settings.home"
                && !tabletRoot.semanticBackUsesSettingsHeader
            width: visible ? semanticNavigation.buttonWidth : 0
            height: parent.height
            radius: 8
            color: backMouse.pressed ? "#161616" : "#2b2b2b"
            border.color: "#75ead5"
            Accessible.id: objectName
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Back")
            Accessible.onPressAction: activate()
            function activate() { tabletRoot.returnToPreviousSemanticScreen() }
            Text {
                anchors.centerIn: parent
                text: qsTr("BACK")
                color: "white"
                font.bold: true
            }
            MouseArea {
                id: backMouse
                anchors.fill: parent
                Accessible.ignored: true
                onClicked: semanticBack.activate()
            }
        }

        Rectangle {
            id: semanticHome
            objectName: "nav.home"
            width: semanticNavigation.buttonWidth
            height: parent.height
            radius: 8
            color: homeMouse.pressed ? "#161616" : "#2b2b2b"
            border.color: "#75ead5"
            Accessible.id: objectName
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Tablet home")
            Accessible.onPressAction: activate()
            function activate() { tabletProxy.gotoHomeScreen() }
            Text {
                anchors.centerIn: parent
                text: qsTr("HOME")
                color: "white"
                font.bold: true
            }
            MouseArea {
                id: homeMouse
                anchors.fill: parent
                Accessible.ignored: true
                onClicked: semanticHome.activate()
            }
        }

        Rectangle {
            id: semanticClose
            objectName: "nav.close"
            width: semanticNavigation.buttonWidth
            height: parent.height
            radius: 8
            color: closeMouse.pressed ? "#169c86" : "#1fc6a6"
            border.color: "#75ead5"
            Accessible.id: objectName
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Close tablet")
            Accessible.onPressAction: activate()
            function activate() { tabletProxy.hideAndroidTablet() }
            Text {
                anchors.centerIn: parent
                text: qsTr("CLOSE")
                color: "#10252d"
                font.bold: true
            }
            MouseArea {
                id: closeMouse
                anchors.fill: parent
                Accessible.ignored: true
                onClicked: semanticClose.activate()
            }
        }
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

    Item {
        id: loader
        objectName: "loader";
        property string source: "";
        property var item: null;
        // One host-level scale covers the status bar, launcher, close control,
        // QML applications and web applications consistently on Android.
        readonly property real contentScale: tabletRoot.screenSpaceMode
            ? tabletRoot.screenSpaceContentScale : 1.0

        transformOrigin: Item.TopLeft
        scale: contentScale
        height: pane.scrollHeight / contentScale
        width: pane.contentWidth / contentScale

        // this might be looking not clear from the first look
        // but loader.parent is not tabletRoot and it can be null!
        // unfortunately we can't use conditional bindings here due to https://bugreports.qt.io/browse/QTBUG-22005

        onParentChanged: {
            if (parent) {
                anchors.left = Qt.binding(function() { return parent.left })
                anchors.top = Qt.binding(function() { return parent.top })
            } else {
                anchors.left = undefined
                anchors.top = undefined
            }
        }

        signal loaded;
        
        onWidthChanged: {
            resizeLoadedItem();
        }
        
        onHeightChanged: {
            resizeLoadedItem();
        }

        onContentScaleChanged: resizeLoadedItem()

        function resizeLoadedItem() {
            if (!loader.item) {
                return;
            }
            loader.item.width = loader.width;
            loader.item.height = loader.height;
        }
        
        function load(newSource, callback) {
            if (Qt.platform.os === "ios") {
                console.info("OVERTE_IOS_TABLET_QML stage=load-requested source=" + newSource +
                    " previous=" + loader.source + " had_item=" + (loader.item !== null))
            }
            if (loader.item) {
                loader.item.destroy();
                loader.item = null;
            }
            
            loader.source = newSource;
            QmlSurface.load(newSource, loader, function(newItem) {
                loader.item = newItem;
                loader.resizeLoadedItem();
                loader.loaded();
                if (loader.item.hasOwnProperty("sendToScript")) {
                    loader.item.sendToScript.connect(tabletRoot.sendToScript);
                }
                if (loader.item.hasOwnProperty("setRootMenu")) {
                    loader.item.setRootMenu(tabletRoot.rootMenu, tabletRoot.subMenu);
                }
                if (Qt.platform.os !== "ios") {
                    loader.item.forceActiveFocus();
                }
                
                if (callback) {
                    callback();
                }                

                var type = "Unknown";
                if (newSource === "") {
                    type = "Closed";
                } else if (newSource === "hifi/tablet/TabletMenu.qml") {
                    type = "Menu";
                } else if (newSource === "hifi/tablet/TabletHome.qml") {
                    type = "Home";
                } else if (newSource === "hifi/tablet/TabletWebView.qml") {
                    // Handled in `callback()`
                    return;
                } else if (newSource.toLowerCase().indexOf(".qml") > -1) {
                    type = "QML";
                } else {
                    console.log("newSource is of unknown type!");
                }
                
                screenChanged(type, newSource);

                if (Qt.platform.os === "ios") {
                    Qt.callLater(function() {
                        if (loader.item !== newItem) {
                            return
                        }
                        loader.item.forceActiveFocus()
                        console.info("OVERTE_IOS_TABLET_QML stage=load-complete source=" + newSource +
                            " class=" + loader.item + " size=" + loader.item.width + "x" + loader.item.height +
                            " visible=" + loader.item.visible + " active_focus=" + loader.item.activeFocus)
                    })
                }
            });
        }
    }


    implicitWidth: 480
    implicitHeight: 706
}
