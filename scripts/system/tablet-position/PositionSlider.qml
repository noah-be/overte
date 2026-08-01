import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ColumnLayout {
    id: root
    property alias value: slider.value
    property alias from: slider.from
    property alias to: slider.to
    property alias stepSize: slider.stepSize
    property string title: ""
    property string suffix: ""
    property int decimals: 2

    Layout.fillWidth: true
    spacing: 4

    RowLayout {
        Layout.fillWidth: true
        Label {
            text: root.title
            color: "white"
            font.pixelSize: 22
            Layout.fillWidth: true
        }
        Label {
            text: slider.value.toFixed(root.decimals) + root.suffix
            color: "white"
            font.pixelSize: 22
            font.bold: true
        }
    }

    Slider {
        id: slider
        Layout.fillWidth: true
        Layout.preferredHeight: 54
        snapMode: Slider.SnapAlways
    }
}
