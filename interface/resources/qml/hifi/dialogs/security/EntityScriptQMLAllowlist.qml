//
//  EntityScriptQMLAllowlist.qml
//  interface/resources/qml/hifi/dialogs/security
//
//  Created by Kalila L. on 2019.12.05 | realities.dev | somnilibertas@gmail.com
//  Copyright 2019 Kalila L.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
// Security Settings for the Entity Script QML Allowlist

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
    HifiStylesUit.HifiConstants { id: hifi }
    SecurityTouchConfiguration {
        id: touchConfiguration
        availableWidth: parentBody.width
        availableHeight: parentBody.height
    }

    function getAllowlistAsText() {
        return SecuritySettings.normalizeAllowlist(
            Settings.getValue("private/settingsSafeURLS", ""));
    }

    function setAllowlistAsText(allowlistText) {
        var normalized = SecuritySettings.normalizeAllowlist(allowlistText);
        Settings.setValue("private/settingsSafeURLS", normalized);
        var stored = SecuritySettings.normalizeAllowlist(
            Settings.getValue("private/settingsSafeURLS", ""));
        setAllowlistSuccess(stored === normalized);
    }

    function setAllowlistSuccess(success) {
        if (success) {
            notificationText.text = "Successfully saved settings.";
        } else {
            notificationText.text = "Error! Settings not saved.";
        }
    }

    function toggleAllowlist(enabled) {
        Settings.setValue("private/allowlistEnabled", enabled);
        console.info("Toggling Allowlist to:", enabled);
    }

    anchors.fill: parent
    width: parent.width;
    height: 120;
    color: "#80010203";

    HifiStylesUit.RalewayRegular {
        id: titleText;
        text: "Entity Script / QML Allowlist"
        // Text size
        size: Math.round(24 * touchConfiguration.textScale);
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

        HiFiControls.CheckBox {
            id: allowlistEnabled;
            checked: Settings.getValue("private/allowlistEnabled", false);

            anchors.right: parent.right;
            anchors.top: parent.top;
            anchors.topMargin: 10;
            height: Math.max(touchConfiguration.buttonHeight,
                touchConfiguration.adaptiveMinimumControlHeight)
            text: qsTr("Enabled")
            labelFontSize: Math.round(18 * touchConfiguration.textScale)
            colorScheme: hifi.colorSchemes.dark
            color: "white"
            Accessible.name: qsTr("Entity script and QML allowlist")
            Accessible.description: qsTr("Restrict entity content to trusted URLs")
            onToggled: {
                toggleAllowlist(allowlistEnabled.checked)
            }
        }
    }

    Rectangle {
        id: editorBody;
        color: "black";
        anchors.top: titleText.bottom;
        anchors.left: parent.left;
        anchors.right: parent.right;
        anchors.bottom: parent.bottom;

        Text {
            id: descriptionText;
            text: "One trusted URL or QML file per line. Changes apply when content reloads.";
            color: "white";
            font.pixelSize: Math.round(14 * touchConfiguration.textScale);
            wrapMode: Text.WordWrap;
            anchors.top: parent.top;
            anchors.left: parent.left;
            anchors.right: parent.right;
            anchors.margins: 10;
            height: paintedHeight;
        }

        ScrollView {
            id: textAreaScrollView;
            anchors.top: descriptionText.bottom;
            anchors.left: parent.left;
            anchors.right: parent.right;
            anchors.bottom: saveChanges.top;
            anchors.margins: 10;
            clip: true;
            ScrollBar.vertical: HiFiControls.ScrollBar { }

            TextArea {
                id: allowlistTextArea;
                text: getAllowlistAsText();
                onTextChanged: notificationText.text = "";
                width: textAreaScrollView.availableWidth;
                font.family: "Ubuntu";
                font.pixelSize: Math.round(16 * touchConfiguration.textScale);
                color: "white";
                wrapMode: TextEdit.NoWrap;
                inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoAutoUppercase
                    | Qt.ImhNoPredictiveText
                Accessible.role: Accessible.EditableText
                Accessible.name: qsTr("Trusted entity URLs")
                Accessible.description: qsTr("One trusted URL or QML file per line")
            }
        }

        HifiStylesUit.RalewayRegular {
            id: notificationText;
            text: "";
            size: Math.round(16 * touchConfiguration.textScale);
            color: "white";
            elide: Text.ElideRight;
            anchors.left: parent.left;
            anchors.right: saveChanges.left;
            anchors.verticalCenter: saveChanges.verticalCenter;
            anchors.margins: 10;
        }

        HiFiControls.Button {
            id: saveChanges;
            anchors.right: parent.right;
            anchors.bottom: parent.bottom;
            anchors.margins: 10;
            height: touchConfiguration.buttonHeight;
            width: 160;
            text: "Save Changes";
            Accessible.name: qsTr("Save entity allowlist")
            Accessible.description: qsTr("Store the edited entity script and QML allowlist")
            androidClickAction: function () {
                setAllowlistAsText(allowlistTextArea.text)
            }
            onClicked: if (Qt.platform.os !== "android") {
                setAllowlistAsText(allowlistTextArea.text)
            }
        }
    }

    Component.onDestruction: {
        allowlistTextArea.focus = false;
        Qt.inputMethod.hide();
    }
}
