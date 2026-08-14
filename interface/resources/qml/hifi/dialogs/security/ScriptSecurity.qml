//
//  ScriptPermissions.cpp
//  libraries/script-engine/src/ScriptPermissions.cpp
//
//  Created by dr Karol Suprynowicz on 2024/03/24.
//  Copyright 2024 Overte e.V.
//
//  Based on EntityScriptQMLAllowlist.qml
//  Created by Kalila L. on 2019.12.05 | realities.dev | somnilibertas@gmail.com
//  Copyright 2019 Kalila L.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
// Security settings for the script engines

import Hifi 1.0 as Hifi
import QtQuick 2.8
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.12
import stylesUit 1.0 as HifiStylesUit
import controlsUit 1.0 as HiFiControls
import PerformanceEnums 1.0
import "../../../windows"
import "SecuritySettings.js" as SecuritySettings


Rectangle {
    id: parentBody;
    SecurityTouchConfiguration {
        id: touchConfiguration
        availableWidth: parentBody.width
        availableHeight: parentBody.height
    }

    function getAllowlistAsText() {
        return SecuritySettings.normalizeAllowlist([
            Settings.getValue("private/scriptPermissionGetAvatarURLSafeURLs", ""),
            Settings.getValue("private/scriptPermissionBookmarksSafeURLs", "")
        ].join("\n"));
    }

    function setAllowlistAsText(allowlistText) {
        var normalized = SecuritySettings.normalizeAllowlist(allowlistText);
        Settings.setValue("private/scriptPermissionGetAvatarURLSafeURLs", normalized);
        Settings.setValue("private/scriptPermissionBookmarksSafeURLs", normalized);
        notificationText.text = "Allowlist saved.";
    }

    function setAvatarProtection(enabled) {
        Settings.setValue("private/scriptPermissionGetAvatarURLEnable", enabled);
        console.info("Setting Protect Avatar URLs to:", enabled);
    }

    function setBookmarkProtection(enabled) {
        Settings.setValue("private/scriptPermissionBookmarksEnable", enabled);
        console.info("Setting Protect Bookmarks to:", enabled);
    }

    anchors.fill: parent
    width: parent.width;
    height: 120;
    color: "#80010203";

    HifiStylesUit.RalewayRegular {
        id: protectAvatars;
        text: "Protect Avatar URLs"
        // Text size
        size: 24;
        // Style
        color: "white";
        elide: Text.ElideRight;
        // Anchors
        anchors.top: parent.top;
        anchors.left: parent.left;
        anchors.leftMargin: 20;
        anchors.right: parent.right;
        anchors.rightMargin: 20;
        height: touchConfiguration.titleHeight;

        CheckBox {
            id: avatarsAllowlistEnabled;

            checked: Settings.getValue("private/scriptPermissionGetAvatarURLEnable", true);

            anchors.right: parent.right;
            anchors.top: parent.top;
            anchors.topMargin: 10;
            onToggled: {
                setAvatarProtection(avatarsAllowlistEnabled.checked)
            }

            Label {
                text: "Enabled"
                color: "white"
                font.pixelSize: 18;
                anchors.right: parent.left;
                anchors.top: parent.top;
                anchors.topMargin: 10;
            }
        }
    }

    HifiStylesUit.RalewayRegular {
        id: protectBookmarks;
        text: "Protect Bookmarks"
        // Text size
        size: 24;
        // Style
        color: "white";
        elide: Text.ElideRight;
        // Anchors
        anchors.top: protectAvatars.bottom;
        anchors.left: parent.left;
        anchors.leftMargin: 20;
        anchors.right: parent.right;
        anchors.rightMargin: 20;
        height: touchConfiguration.titleHeight;

        CheckBox {
            id: bookmarksAllowlistEnabled;

            checked: Settings.getValue("private/scriptPermissionBookmarksEnable", true);

            anchors.right: parent.right;
            anchors.top: parent.top;
            anchors.topMargin: 10;
            onToggled: {
                setBookmarkProtection(bookmarksAllowlistEnabled.checked)
            }

            Label {
                text: "Enabled"
                color: "white"
                font.pixelSize: 18;
                anchors.right: parent.left;
                anchors.top: parent.top;
                anchors.topMargin: 10;
            }
        }
    }

    HifiStylesUit.RalewayRegular {
        id: allowedURLsTitle;
        text: "Trusted Scripts";
        // Text size
        size: 24;
        // Style
        color: "white";
        elide: Text.ElideRight;
        // Anchors
        anchors.top: protectBookmarks.bottom;
        anchors.left: parent.left;
        anchors.leftMargin: 20;
        anchors.right: parent.right;
        anchors.rightMargin: 20;
        height: touchConfiguration.titleHeight;
    }

    Rectangle {
        id: textAreaRectangle;
        color: "black";
        width: parent.width;
        anchors.top: allowedURLsTitle.bottom;
        anchors.bottom: saveChanges.top;
        anchors.bottomMargin: 20;

        ScrollView {
            id: textAreaScrollView
            anchors.fill: parent;
            width: parent.width
            contentWidth: parent.width
            contentHeight: parent.height
            clip: false;

            TextArea {
                id: allowlistTextArea
                text: getAllowlistAsText();
                placeholderText: "https://example.com/allowedScript.js\nhttps://example.com/anotherAllowedScript.js";
                onTextChanged: notificationText.text = "";
                width: parent.width;
                height: parent.height;
                font.family: "Ubuntu";
                font.pointSize: 12;
                color: "white";
            }
        }
    }

    Button {
        id: saveChanges
        anchors.topMargin: 20;
        anchors.leftMargin: 20;
        anchors.rightMargin: 20;
        anchors.bottomMargin: 20;
        anchors.right: parent.right;
        anchors.bottom: parent.bottom;
        contentItem: Text {
            text: saveChanges.text
            font.family: "Ubuntu";
            font.pointSize: 12;
            opacity: enabled ? 1.0 : 0.3
            color: "black"
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        text: "Save Changes"
        height: touchConfiguration.buttonHeight;
        onClicked: setAllowlistAsText(allowlistTextArea.text)

        HifiStylesUit.RalewayRegular {
            id: notificationText;
            text: ""
            // Text size
            size: 16;
            // Style
            color: "white";
            elide: Text.ElideLeft;
            // Anchors
            anchors.right: parent.left;
            anchors.rightMargin: 10;
        }
    }

    Component.onDestruction: {
        allowlistTextArea.focus = false;
        Qt.inputMethod.hide();
    }
}
