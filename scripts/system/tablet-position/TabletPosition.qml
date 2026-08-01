import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    width: 480
    height: 706
    color: "#191919"
    signal sendToScript(var message)

    property bool initialized: false

    function applyValues() {
        sendToScript({
            type: "applyTabletPosition",
            forward: distanceSlider.value,
            up: heightSlider.value,
            tilt: tiltSlider.value
        })
    }

    function fromScript(message) {
        if (!message || message.type !== "values") {
            return
        }
        distanceSlider.value = Number(message.forward)
        heightSlider.value = Number(message.up)
        tiltSlider.value = Number(message.tilt)
        initialized = true
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 18

        Label {
            text: "Tablet Position"
            color: "white"
            font.pixelSize: 34
            font.bold: true
            Layout.fillWidth: true
        }

        Label {
            text: "Set the tablet's default position. Changes take effect immediately after Apply."
            color: "#cccccc"
            font.pixelSize: 18
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        PositionSlider {
            id: distanceSlider
            title: "Distance"
            suffix: " m"
            from: 0.4
            to: 2.0
            stepSize: 0.05
            decimals: 2
        }

        PositionSlider {
            id: heightSlider
            title: "Height offset"
            suffix: " m"
            from: -1.3
            to: 0.3
            stepSize: 0.05
            decimals: 2
        }

        PositionSlider {
            id: tiltSlider
            title: "Tilt"
            suffix: "°"
            from: -45
            to: 30
            stepSize: 1
            decimals: 0
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Button {
                text: "Reset"
                font.pixelSize: 20
                Layout.fillWidth: true
                Layout.preferredHeight: 58
                onClicked: {
                    distanceSlider.value = 1.25
                    heightSlider.value = -0.52
                    tiltSlider.value = -18
                }
            }

            Button {
                text: "Apply"
                font.pixelSize: 20
                font.bold: true
                Layout.fillWidth: true
                Layout.preferredHeight: 58
                enabled: root.initialized
                onClicked: root.applyValues()
            }
        }
    }
}
