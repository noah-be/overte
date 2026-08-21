import QtQuick 2.7
import controlsUit 1.0 as HifiControls

Item {
    id: root
    anchors.fill: parent
    signal sendToScript(var message)

    property string activeEmote: ""
    property string statusText: qsTr("Choose an emote")
    readonly property var emotes: [
        "Crying", "Surprised", "Dancing", "Cheering", "Waving",
        "Fall", "Pointing", "Clapping", "Sit", "Love"
    ]

    HifiControls.TouchUiMetrics {
        id: touchMetrics
        availableWidth: root.width
        availableHeight: root.height
    }

    Rectangle {
        anchors.fill: parent
        color: "#17212a"
    }

    Column {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        Text {
            width: parent.width
            text: qsTr("EMOTE")
            color: "white"
            font.pixelSize: Math.round(24 * touchMetrics.textScale)
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            Accessible.role: Accessible.StaticText
            Accessible.name: text
        }

        Text {
            objectName: "PhoneEmoteStatus"
            width: parent.width
            height: Math.max(24, implicitHeight)
            text: root.statusText
            color: root.activeEmote.length > 0 ? "#00b4ef" : "#d9e2e8"
            font.pixelSize: Math.round(14 * touchMetrics.textScale)
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            Accessible.role: Accessible.StaticText
            Accessible.name: text
        }

        GridView {
            id: emoteGrid
            objectName: "PhoneEmoteGrid"
            width: parent.width
            height: parent.height - y
            readonly property int adaptiveColumns: touchMetrics.columnsFor(
                140 * touchMetrics.textScale, 4, 2)
            cellWidth: width / adaptiveColumns
            cellHeight: Math.max(54, touchMetrics.adaptiveMinimumControlHeight)
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            pressDelay: touchMetrics.pressDelay
            flickDeceleration: touchMetrics.flickDeceleration
            maximumFlickVelocity: touchMetrics.maximumFlickVelocity
            model: root.emotes

            delegate: Item {
                width: emoteGrid.cellWidth
                height: emoteGrid.cellHeight

                HifiControls.Button {
                    objectName: "PhoneEmoteButton_" + modelData
                    anchors.fill: parent
                    anchors.margins: 4
                    text: modelData
                    fontSize: Math.round(15 * touchMetrics.textScale)
                    highlighted: root.activeEmote === modelData
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: modelData
                    Accessible.description: root.activeEmote === modelData
                        ? qsTr("Currently playing emote")
                        : qsTr("Play emote")
                    androidClickAction: function () {
                        root.sendToScript({
                            method: "phoneEmote.play",
                            name: modelData
                        })
                    }
                }
            }
        }
    }

    function fromScript(message) {
        if (!message || message.method !== "phoneEmote.state") {
            return
        }
        activeEmote = typeof message.active === "string" ? message.active : ""
        statusText = typeof message.status === "string" && message.status.length > 0
            ? message.status
            : qsTr("Choose an emote")
    }

    Component.onCompleted: sendToScript({ method: "phoneEmote.ready" })
}
