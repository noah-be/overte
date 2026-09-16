//
//  Preference.qml
//
//  Created by Bradley Austin Davis on 18 Jan 2016
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.5

Item {
    id: root
    anchors { left: parent.left; right: parent.right }
    property var preference;
    property string label: preference ? preference.name : "";
    property bool isFirstCheckBox;
    readonly property bool profileAllowed: !preference || preference.profileAllowed === true
    visible: profileAllowed
    enabled: profileAllowed && (!preference || preference.enabled)
    activeFocusOnTab: false
    Component.onCompleted: {
        if (preference && profileAllowed) {
            preference.load();
        }
    }

    function restore() { }
}
