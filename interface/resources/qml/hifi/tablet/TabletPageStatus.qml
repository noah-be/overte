import QtQuick 2.7
import QtQuick.Controls 2.3

Item {
    id: status
    property bool failed: false
    signal homeRequested()
    Column {
        anchors.centerIn: parent
        width: Math.max(0, parent.width - 32)
        spacing: 16
        BusyIndicator {
            anchors.horizontalCenter: parent.horizontalCenter
            running: status.visible && !status.failed
            visible: !status.failed
        }
        Label {
            width: parent.width
            text: status.failed ? qsTr("This app could not be opened.") : qsTr("Opening app…")
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }
        Button {
            objectName: "tablet.load-error.home"
            anchors.horizontalCenter: parent.horizontalCenter
            text: qsTr("Home")
            height: Math.max(48, implicitHeight)
            onClicked: status.homeRequested()
        }
    }
}
