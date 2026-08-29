//
//  Security.qml
//  qml\hifi\dialogs\security
//
//  Security
//
//  Created by Zach Fox on 2018-10-31
//  Copyright 2018 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import Hifi 1.0 as Hifi
import QtQuick 2.5
import Qt5Compat.GraphicalEffects
import stylesUit 1.0 as HifiStylesUit
import controlsUit 1.0 as HifiControlsUit
import "qrc:/qml/controls" as HifiControls

Rectangle {
    HifiStylesUit.HifiConstants { id: hifi; }
    SecurityTouchConfiguration {
        id: touchConfiguration
        availableWidth: root.width
        availableHeight: root.height
    }

    id: root;
    objectName: "settings.security"
    color: hifi.colors.baseGray;
    
    property string title: "Security Settings";
    
    QtObject {
        id: margins
        property real paddings: root.width / 20.25

        property real sizeCheckBox: root.width / 13.5
        property real sizeText: root.width / 2.5
        property real sizeLevel: root.width / 5.8
        property real sizeDesktop: root.width / 5.8
        property real sizeVR: root.width / 13.5
    }

    // Username Text
    HifiStylesUit.RalewayRegular {
        id: usernameText;
        text: Account.username === "Unknown user" ? "Please Log In" : Account.username;
        // Text size
        size: Math.round(24 * touchConfiguration.textScale);
        // Style
        color: hifi.colors.white;
        elide: Text.ElideRight;
        // Anchors
        anchors.top: parent.top;
        anchors.left: parent.left;
        anchors.leftMargin: 20;
        anchors.right: parent.right;
        anchors.rightMargin: 20;
        height: touchConfiguration.titleHeight;
    }

    Item {
        id: pleaseLogInContainer;
        visible: Account.username === "Unknown user";
        anchors.top: usernameText.bottom;
        anchors.left: parent.left;
        anchors.right: parent.right;
        anchors.bottom: parent.bottom;

        HifiStylesUit.RalewayRegular {
            text: "Please log in for security settings."
            // Text size
            size: Math.round(24 * touchConfiguration.textScale);
            // Style
            color: hifi.colors.white;
            // Anchors
            anchors.bottom: openLoginButton.top;
            anchors.left: parent.left;
            anchors.right: parent.right;
            horizontalAlignment: Text.AlignHCenter;
            verticalAlignment: Text.AlignVCenter;
            height: 60;
        }
        
        HifiControlsUit.Button {
            id: openLoginButton;
            color: hifi.buttons.white;
            colorScheme: hifi.colorSchemes.dark;
            anchors.centerIn: parent;
            width: 140;
            height: touchConfiguration.buttonHeight;
            text: "Log In";
            onClicked: {
                DialogsManager.showLoginDialog();
            }
        }
    }

    Item {
        id: securitySettingsContainer;
        visible: !pleaseLogInContainer.visible;
        anchors.top: usernameText.bottom;
        anchors.left: parent.left;
        anchors.right: parent.right;
        anchors.bottom: parent.bottom;

        Item {
            id: accountContainer;
            anchors.top: securitySettingsContainer.top;
            anchors.left: parent.left;
            anchors.right: parent.right;
            height: childrenRect.height;

            Rectangle {
                id: accountHeaderContainer;
                anchors.top: parent.top;
                anchors.left: parent.left;
                anchors.right: parent.right;
                height: touchConfiguration.headerHeight;
                color: hifi.colors.baseGrayHighlight;

                HifiStylesUit.RalewaySemiBold {
                    text: "Account";
                    anchors.fill: parent;
                    anchors.leftMargin: 20;
                    color: hifi.colors.white;
                    size: Math.round(18 * touchConfiguration.textScale);
                }
            }

            Item {
                id: keepMeLoggedInContainer;
                anchors.top: accountHeaderContainer.bottom;
                anchors.left: parent.left;
                anchors.right: parent.right;
                height: touchConfiguration.rowHeight;

                HifiControlsUit.CheckBox {
                    id: autoLogoutCheckbox;
                    checked: Settings.getValue("keepMeLoggedIn", false);
                    text: "Keep Me Logged In"
                    // Anchors
                    anchors.verticalCenter: parent.verticalCenter;
                    anchors.left: parent.left;
                    anchors.leftMargin: 20;
                    boxSize: 24;
                    labelFontSize: 18;
                    colorScheme: hifi.colorSchemes.dark
                    color: hifi.colors.white;
                    width: 240;
                    onCheckedChanged: {
                        Settings.setValue("keepMeLoggedIn", checked);
                        if (checked) {
                            Settings.setValue("keepMeLoggedIn/savedUsername", Account.username);
                        } else {
                            Settings.setValue("keepMeLoggedIn/savedUsername", "");
                        }
                    }
                }

                HifiStylesUit.RalewaySemiBold {
                    id: autoLogoutHelp;
                    function showHelp() {
                        lightboxPopup.titleText = "Keep Me Logged In";
                        lightboxPopup.bodyText = "If you choose to stay logged in, ensure that this is a trusted device.\n\n" +
                            "Also, remember that logging out may not disconnect you from a domain.";
                        lightboxPopup.button1text = "OK";
                        lightboxPopup.button1method = function() {
                            lightboxPopup.visible = false;
                        }
                        lightboxPopup.visible = true;
                    }
                    text: '[?]';
                    // Anchors
                    anchors.verticalCenter: parent.verticalCenter;
                    anchors.right: autoLogoutCheckbox.right;
                    width: Math.max(30, touchConfiguration.adaptiveMinimumControlHeight);
                    height: Math.max(30, touchConfiguration.adaptiveMinimumControlHeight);
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: qsTr("Keep me logged in help")
                    Accessible.description: qsTr("Explain persistent login")
                    Accessible.onPressAction: showHelp()
                    // Text size
                    size: Math.round(18 * touchConfiguration.textScale);
                    // Style
                    color: hifi.colors.blueHighlight;

                    MouseArea {
                        anchors.fill: parent;
                        Accessible.ignored: true
                        hoverEnabled: touchConfiguration.hoverSupported;
                        onEntered: {
                            parent.color = hifi.colors.blueAccent;
                        }
                        onExited: {
                            parent.color = hifi.colors.blueHighlight;
                        }
                        onClicked: autoLogoutHelp.showHelp()
                    }
                    Keys.onReturnPressed: showHelp()
                    Keys.onEnterPressed: showHelp()
                    Keys.onSpacePressed: showHelp()
                }
            }
        }

        // -- Plugin Permissions --
        Item {
            id: kpiContainer;
            visible: touchConfiguration.showScriptingPlugins;
            anchors.top: accountContainer.bottom;
            anchors.left: parent.left;
            anchors.right: parent.right;
            height: visible ? childrenRect.height : 0;

            Rectangle {
                id: kpiHeaderContainer;
                anchors.top: parent.top;
                anchors.left: parent.left;
                anchors.right: parent.right;
                height: touchConfiguration.headerHeight;
                color: hifi.colors.baseGrayHighlight;

                HifiStylesUit.RalewaySemiBold {
                    text: "Plugin Permissions";
                    anchors.fill: parent;
                    anchors.leftMargin: 20;
                    color: hifi.colors.white;
                    size: Math.round(18 * touchConfiguration.textScale);
                }
            }

            Item {
                id: kpiScriptContainer;
                anchors.top: kpiHeaderContainer.bottom;
                anchors.left: parent.left;
                anchors.right: parent.right;
                height: touchConfiguration.rowHeight;

                HifiControlsUit.CheckBox {
                    id: kpiScriptCheckbox;
                    readonly property string kpiSettingsKey: "private/enableScriptingPlugins"
                    checked: Settings.getValue(kpiSettingsKey, false);
                    text: "Enable custom script plugins (requires restart)"
                    // Anchors
                    anchors.verticalCenter: parent.verticalCenter;
                    anchors.left: parent.left;
                    anchors.leftMargin: 20;
                    boxSize: 24;
                    labelFontSize: 18;
                    colorScheme: hifi.colorSchemes.dark
                    color: hifi.colors.white;
                    width: 300;
                    onCheckedChanged: {
                        if (touchConfiguration.showScriptingPlugins) {
                            Settings.setValue(kpiSettingsKey, checked);
                        }
                    }
                }

                HifiStylesUit.RalewaySemiBold {
                    id: kpiScriptHelp;
                    function showHelp() {
                        lightboxPopup.titleText = "Script Plugin Infrastructure";
                        lightboxPopup.bodyText = "Toggles the activation of scripting plugins in the 'plugins/scripting' folder. \n\n"
                          + "Created by:\n    humbletim@gmail.com\n    somnilibertas@gmail.com";
                        lightboxPopup.button1text = "OK";
                        lightboxPopup.button1method = function() {
                            lightboxPopup.visible = false;
                        }
                        lightboxPopup.visible = true;
                    }
                    text: '[?]';
                    // Anchors
                    anchors.verticalCenter: parent.verticalCenter;
                    anchors.left: kpiScriptCheckbox.right;
                    width: Math.max(30, touchConfiguration.adaptiveMinimumControlHeight);
                    height: Math.max(30, touchConfiguration.adaptiveMinimumControlHeight);
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: qsTr("Script plugins help")
                    Accessible.description: qsTr("Explain custom script plugins")
                    Accessible.onPressAction: showHelp()
                    // Text size
                    size: Math.round(18 * touchConfiguration.textScale);
                    // Style
                    color: hifi.colors.blueHighlight;

                    MouseArea {
                        anchors.fill: parent;
                        Accessible.ignored: true
                        hoverEnabled: touchConfiguration.hoverSupported;
                        onEntered: {
                            parent.color = hifi.colors.blueAccent;
                        }
                        onExited: {
                            parent.color = hifi.colors.blueHighlight;
                        }
                        onClicked: kpiScriptHelp.showHelp()
                    }
                    Keys.onReturnPressed: showHelp()
                    Keys.onEnterPressed: showHelp()
                    Keys.onSpacePressed: showHelp()
                }
            }
        }
    }
}
