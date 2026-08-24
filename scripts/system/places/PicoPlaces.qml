import QtQuick 2.7
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3

Rectangle {
    id: root
    color: "#303030"

    signal sendToScript(var message)
    property string channel: "com.overte.places"
    property bool loading: true

    ListModel {
        id: placesModel
    }

    function requestContent() {
        loading = true;
        sendToScript({
            channel: channel,
            action: "READY_FOR_CONTENT"
        });
    }

    function fromScript(message) {
        if (!message || message.channel !== channel) {
            return;
        }
        if (message.action === "PLACE_DATA") {
            placesModel.clear();
            var records = message.data || [];
            for (var i = 0; i < records.length; ++i) {
                var place = records[i];
                // Utility entries such as Home and Tutorial use the same
                // address field and are useful on the standalone client too.
                placesModel.append({
                    placeName: place.name || place.address || "Unnamed place",
                    placeAddress: place.address || "",
                    placeDescription: place.description || "",
                    attendance: Number(place.current_attendance || 0),
                    capacity: Number(place.capacity || 0),
                    region: place.metaverseRegion || ""
                });
            }
            loading = false;
        }
    }

    Component.onCompleted: {
        console.log("OVERTE_IOS_TOUCH_UI_GATE stage=places-qml-ready")
        requestContent()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        RowLayout {
            Layout.fillWidth: true

            Text {
                text: "OVERTE PLACES"
                color: "white"
                font.pixelSize: 24
                font.bold: true
                Layout.fillWidth: true
            }

            Button {
                text: "Refresh"
                enabled: !root.loading
                onClicked: root.requestContent()
            }
        }

        Text {
            Layout.fillWidth: true
            visible: root.loading
            text: "Loading current domain directory..."
            color: "#b8e6ff"
            font.pixelSize: 18
            horizontalAlignment: Text.AlignHCenter
        }

        Text {
            Layout.fillWidth: true
            visible: !root.loading && placesModel.count === 0
            text: "No compatible online places found."
            color: "#dddddd"
            font.pixelSize: 18
            horizontalAlignment: Text.AlignHCenter
        }

        ListView {
            id: placesList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 8
            model: placesModel

            ScrollBar.vertical: ScrollBar {}

            delegate: Rectangle {
                width: placesList.width
                height: Math.max(82, content.implicitHeight + 22)
                radius: 6
                color: mouseArea.pressed ? "#267faa" : (mouseArea.containsMouse ? "#3f6f82" : "#454545")
                border.color: "#707070"

                Column {
                    id: content
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 14
                    spacing: 4

                    Row {
                        width: parent.width
                        spacing: 10

                        Text {
                            width: parent.width - users.width - 10
                            text: placeName
                            color: "white"
                            font.pixelSize: 20
                            font.bold: true
                            elide: Text.ElideRight
                        }

                        Text {
                            id: users
                            text: capacity > 0 ? attendance + "/" + capacity : attendance + " online"
                            color: attendance > 0 ? "#76e09a" : "#bbbbbb"
                            font.pixelSize: 16
                        }
                    }

                    Text {
                        width: parent.width
                        text: placeDescription || placeAddress
                        color: "#dddddd"
                        font.pixelSize: 15
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: mouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        if (placeAddress !== "") {
                            root.sendToScript({
                                channel: root.channel,
                                action: "TELEPORT",
                                name: placeName,
                                address: placeAddress
                            });
                        }
                    }
                }
            }
        }
    }
}
