import QtQuick 2.7
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3

RowLayout {
    id: root
    property var fields: []
    property real step: 0.01
    signal numericFocusChanged(var field, bool focused, real step)
    Layout.fillWidth: true
    spacing: 10

    Repeater {
        model: 3
        TextField {
            Layout.fillWidth: true
            font.pixelSize: 17
            inputMethodHints: Qt.ImhFormattedNumbersOnly
            text: root.fields.length > index ? root.fields[index].text : "0"
            onTextChanged: {
                if (root.fields.length > index && root.fields[index].text !== text) {
                    root.fields[index].text = text;
                }
            }
            onActiveFocusChanged: root.numericFocusChanged(this, activeFocus, root.step)
            Text {
                anchors.left: parent.left
                anchors.leftMargin: 8
                anchors.top: parent.top
                anchors.topMargin: -12
                text: ["X", "Y", "Z"][index]
                color: "#b8e6ff"
                font.pixelSize: 11
            }
        }
    }
}
