// Dedicated test-build fixture; uses the same control as product settings.
import QtQuick 2.7
import controlsUit 1.0 as Uit

FocusScope {
    id: panel
    objectName: "overte-e2e-text-panel"
    width: parent ? parent.width : 640
    height: parent ? parent.height : 360
    z: 100000
    visible: false
    property int submittedCount: 0
    Rectangle { anchors.fill: parent; color: "#20242a" }
    Text {
        anchors.bottom: editor.top
        anchors.bottomMargin: 16
        anchors.horizontalCenter: parent.horizontalCenter
        text: qsTr("Test text input")
        color: "white"
        font.pixelSize: 24
    }
    Uit.TextField {
        id: editor
        objectName: "controlled.text"
        Accessible.role: Accessible.EditableText
        Accessible.name: qsTr("Test text input")
        width: Math.min(560, parent.width - 48)
        anchors.centerIn: parent
        selectByMouse: true
        onAccepted: panel.submittedCount += 1
    }
}
