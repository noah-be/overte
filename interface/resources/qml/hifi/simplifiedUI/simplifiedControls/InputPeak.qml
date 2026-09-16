//
//  InputPeak.qml
//
//  Created by Zach Pomerantz on 6/20/2017
//  Copyright 2017 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.10
import "../../audio" as SharedAudio

Item {
    property var peak
    property alias showMuted: status.visible

    width: 70
    height: 8

    QtObject {
        id: colors

        readonly property string unmuted: "#FFF"
        readonly property string muted: "#E2334D"
        readonly property string gutter: "#575757"
        readonly property string greenStart: "#39A38F"
        readonly property string greenEnd: "#1FC6A6"
        readonly property string yellow: "#C0C000"
        readonly property string red: colors.muted
        readonly property string fill: "#55000000"
    }


    Text {
        id: status

        anchors {
            horizontalCenter: parent.horizontalCenter
            verticalCenter: parent.verticalCenter
        }

        visible: false
        color: colors.muted

        text: "MUTED"
        font.pointSize: 10
    }

    Item {
        id: bar

        width: parent.width
        height: parent.height

        anchors { fill: parent }

        visible: !status.visible

        SharedAudio.LevelMeter {
            anchors.fill: parent
            level: peak
            gutter: colors.gutter
            low: colors.greenStart
            middle: colors.greenEnd
            high: colors.yellow
        }
    }
}
