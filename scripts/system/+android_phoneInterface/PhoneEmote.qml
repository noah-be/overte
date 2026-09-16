import QtQuick 2.7
import QtQuick.Controls 2.2

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
            font.pixelSize: 24
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            Accessible.role: Accessible.StaticText
            Accessible.name: text
        }

        Text {
            objectName: "PhoneEmoteStatus"
            width: parent.width
            height: 24
            text: root.statusText
            color: root.activeEmote.length > 0 ? "#00b4ef" : "#d9e2e8"
            font.pixelSize: 14
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            Accessible.role: Accessible.StaticText
            Accessible.name: text
        }

        GridView {
            id: emoteGrid
            width: parent.width
            height: parent.height - y
            cellWidth: width / 2
            cellHeight: 54
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: root.emotes

            delegate: Item {
                width: emoteGrid.cellWidth
                height: emoteGrid.cellHeight

                Button {
                    objectName: "PhoneEmoteButton_" + modelData
                    anchors.fill: parent
                    anchors.margins: 4
                    text: modelData
                    font.pixelSize: 15
                    highlighted: root.activeEmote === modelData
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: modelData
                    Accessible.description: root.activeEmote === modelData
                        ? qsTr("Currently playing emote")
                        : qsTr("Play emote")
                    onClicked: root.sendToScript({
                        method: "phoneEmote.play",
                        name: modelData
                    })
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
