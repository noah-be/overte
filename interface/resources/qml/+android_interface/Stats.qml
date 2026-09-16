import Hifi 1.0 as Hifi
import QtQuick 2.3

Item {
    id: stats
    objectName: "StatsItem"
    property int modality: Qt.NonModal
    implicitWidth: fpsBackground.width
    implicitHeight: fpsBackground.height
    z: 10000
    anchors.top: parent ? parent.top : undefined
    anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined
    anchors.topMargin: 18

    Hifi.Stats {
        id: root
        objectName: "Stats"

        Rectangle {
            id: fpsBackground
            width: fpsText.implicitWidth + 24
            height: fpsText.implicitHeight + 14
            radius: 8
            color: "#b0000000"

            Text {
                id: fpsText
                anchors.centerIn: parent
                text: root.presentrate.toFixed(0) + " FPS"
                color: root.presentrate >= 71.0 ? "#76ff76"
                    : root.presentrate >= 60.0 ? "#ffdc63" : "#ff7070"
                font.pixelSize: 24
                font.bold: true
            }
        }
    }
}
