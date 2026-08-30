//
//  TabletGeneralPreferences.qml
//
//  Created by Dante Ruiz on 9 Feb 2017
//  Copyright 2017 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.7
import QtQuick.Controls 2.2
import "tabletWindows"
import "../../dialogs"

StackView {
    id: profileRoot
    TabletGeneralPreferencesPolicy { id: preferencesPolicy }
    initialItem: root
    objectName: "stack"
    readonly property string semanticScreenId: "settings.general"
    property string title: "General Settings"
    property alias gotoPreviousApp: root.gotoPreviousApp;
    property alias gotoPreviousAppFromScript: root.gotoPreviousAppFromScript;
    signal sendToScript(var message);

    function pushSource(path) {
        var item = Qt.createComponent(Qt.resolvedUrl(path));
        profileRoot.push(item);
    }

    function popSource() {
        profileRoot.pop();
    }

    function emitSendToScript(message) {
        profileRoot.sendToScript(message);
    }

    TabletPreferencesDialog {
        id: root
        objectName: "TabletGeneralPreferences"
        showCategories: preferencesPolicy.allowedCategories
        categorySemanticIds: preferencesPolicy.categorySemanticIds
    }

    Rectangle {
        id: semanticBackButton
        z: 1000
        width: 104
        height: 52
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 8
        radius: 6
        color: semanticBackMouseArea.pressed ? "#169c86" : "#1fc6a6"

        Text {
            anchors.centerIn: parent
            text: qsTr("BACK")
            color: "#10252d"
            font.bold: true
            font.pixelSize: 18
        }

        MouseArea {
            id: semanticBackMouseArea
            objectName: "nav.back"
            anchors.fill: parent
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: qsTr("Back to settings")
            Accessible.description: qsTr("Return to the settings category list")
            function activate() {
                profileRoot.emitSendToScript({ type: "returnToSettings" })
            }
            Accessible.onPressAction: activate()
            onClicked: activate()
            Keys.onReturnPressed: activate()
            Keys.onEnterPressed: activate()
            Keys.onSpacePressed: activate()
        }
    }
}
